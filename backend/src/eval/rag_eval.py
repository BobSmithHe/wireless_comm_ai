"""RAG evaluation using LLM-as-judge with per-document scoring."""
import json
import re
import asyncio
import os
from pymilvus import MilvusClient
from ..core.rag.rag_search import rag_search
from ..core.llm.client import DeepSeekClient

TEST_QUESTIONS = [
    "OFDM循环前缀的作用是什么？",
    "OFDM子载波间隔如何选择？",
    "OFDM为什么能对抗频率选择性衰落？",
    "OFDM中IFFT的作用是什么？",
    "OFDM的PAPR问题如何解决？",
    "OFDMA和OFDM的区别是什么？",
    "香农信道容量公式是什么？",
    "瑞利衰落有什么特点？",
    "莱斯衰落和瑞利衰落的区别？",
    "大尺度衰落和小尺度衰落的区别？",
    "多普勒频移如何影响无线通信？",
    "相干带宽和时延扩展的关系？",
    "MIMO空间复用原理是什么？",
    "MIMO分集增益和复用增益的区别？",
    "大规模MIMO的优势？",
    "波束赋形和预编码的关系？",
    "MIMO信道容量随天线数如何增长？",
    "MU-MIMO和SU-MIMO的区别？",
    "LDPC码的基本原理？",
    "Polar码为什么被5G选用？",
    "Turbo码和LDPC码的区别？",
    "信道编码中码率和纠错能力的权衡？",
    "5G NR的子载波间隔有哪几种？",
    "5G NR帧结构特点？",
    "5G NR中PDSCH的MCS表有几种？",
    "5G NR控制信道编码方案？",
    "3GPP 38.211标准主要内容？",
    "QPSK和16QAM的误码率性能对比？",
    "QAM调制的原理？",
    "最大似然检测原理？",
    "MMSE检测和ZF检测的区别？",
    "信道估计中导频设计原则？",
    "LS和MMSE信道估计的区别？",
    "压缩感知在信道估计中的应用？",
    "分集技术的分类有哪些？",
    "最大比合并原理？",
    "选择合并和等增益合并的区别？",
    "Alamouti空时编码原理？",
    "毫米波通信的主要挑战？",
]


def extract_json(raw: str) -> dict:
    """Robust JSON extraction from LLM output."""
    raw = raw.strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw).strip()
    m = re.search(r'\{[\s\S]*\}', raw)
    if m:
        return json.loads(m.group(0))
    raise ValueError("No JSON found in response")


QUERY_GEN_PROMPT = """用户提问：{question}

为检索知识库（含中文教材和英文3GPP协议），生成一个中英双语搜索查询词。
只输出查询词，不要其他内容。例如：
问题：OFDM子载波间隔
输出：OFDM子载波间隔 subcarrier spacing 3GPP NR

问题：{question}
输出："""

JUDGE_PROMPT = """评估以下检索结果能否回答用户问题。对每篇文档单独评分。

用户问题：{query}

检索结果：
{docs}

输出 JSON（不要其他文字）：
{{
    "can_answer": true/false,
    "best_doc": 1-5,
    "overall_score": 0-3,
    "doc_scores": [0-3, 0-3, 0-3, 0-3, 0-3],
    "reason": "一句话"
}}

评分标准：
0 - 不相关
1 - 部分相关但信息不足
2 - 基本可回答
3 - 完全相关，信息充分"""


async def generate_search_query(llm: DeepSeekClient, question: str) -> str:
    """Generate a bilingual search query from the user question."""
    prompt = QUERY_GEN_PROMPT.format(question=question)
    try:
        raw = await llm.raw_chat([{"role": "user", "content": prompt}], temperature=0.0, max_tokens=128)
        return raw.strip()
    except Exception:
        return question


async def evaluate_single(llm: DeepSeekClient, question: str, hits: list[dict]) -> dict:
    docs_text = ""
    for i, h in enumerate(hits[:5]):
        entity = h.get("entity", h)
        content = entity.get("content", "")[:600]
        title = entity.get("parent_title_key", "")
        docs_text += f"\n[文档{i+1}] title={title}\n{content}\n"

    prompt = JUDGE_PROMPT.format(query=question, docs=docs_text)
    try:
        raw = await llm.raw_chat([{"role": "user", "content": prompt}], temperature=0.0, max_tokens=512)
        result = extract_json(raw)
    except Exception as e:
        result = {"can_answer": False, "best_doc": 0, "overall_score": 0, "doc_scores": [0]*5, "reason": f"解析失败: {e}"}
    return result


def format_hits(hits: list[dict]) -> list[dict]:
    """Extract key info from hits for debugging."""
    return [
        {
            "rank": i + 1,
            "title": h.get("entity", h).get("parent_title_key", ""),
            "content_preview": h.get("entity", h).get("content", "")[:200],
            "rrf_score": h.get("rrf_score"),
            "llm_score": h.get("llm_score"),
        }
        for i, h in enumerate(hits)
    ]


async def run_evaluation() -> dict:
    from ..core.config import get_settings
    s = get_settings()

    client = MilvusClient(uri=s.milvus_uri)
    llm = DeepSeekClient()

    results = []
    for i, q in enumerate(TEST_QUESTIONS):
        print(f"[{i+1}/{len(TEST_QUESTIONS)}] {q[:50]}...")
        hits = rag_search(client, q, retrieve_k=30, final_k=5)
        judge = await evaluate_single(llm, q, hits)
        judge["query"] = q
        judge["hits"] = format_hits(hits)
        results.append(judge)

    total = len(results)
    can_answer = sum(1 for r in results if r.get("can_answer"))
    scores = [r.get("overall_score") or 0 for r in results]
    best_docs = [r.get("best_doc") or 0 for r in results]

    # Per-doc stats
    doc_scores = [r.get("doc_scores", [0]*5) for r in results]
    top1_relevant = sum(1 for ds in doc_scores if ds[0] >= 2) if doc_scores else 0
    top3_relevant = sum(1 for ds in doc_scores if sum(1 for s in ds[:3] if s >= 2) > 0)
    top5_relevant = sum(1 for ds in doc_scores if sum(1 for s in ds if s >= 2) > 0)

    metrics = {
        "total_questions": total,
        "can_answer_rate": round(can_answer / total * 100, 1) if total else 0,
        "avg_overall_score": round(sum(scores) / total, 2) if total else 0,
        "best_doc_at_1": sum(1 for d in best_docs if d == 1),
        "best_doc_within_3": sum(1 for d in best_docs if 1 <= d <= 3),
        "best_doc_within_5": sum(1 for d in best_docs if d >= 1),
        "top1_relevant_rate": round(top1_relevant / total * 100, 1) if total else 0,
        "top3_relevant_rate": round(top3_relevant / total * 100, 1) if total else 0,
        "top5_relevant_rate": round(top5_relevant / total * 100, 1) if total else 0,
        "score_distribution": {
            "3分": scores.count(3),
            "2分": scores.count(2),
            "1分": scores.count(1),
            "0分": scores.count(0),
        },
        "details": results,
    }
    return metrics


def main():
    metrics = asyncio.run(run_evaluation())
    print("\n" + "=" * 60)
    print("RAG Evaluation Results")
    print("=" * 60)
    print(f"Questions:          {metrics['total_questions']}")
    print(f"Can Answer Rate:    {metrics['can_answer_rate']}%")
    print(f"Avg Overall Score:  {metrics['avg_overall_score']}/3")
    print(f"Best Doc @1:        {metrics['best_doc_at_1']}/{metrics['total_questions']}")
    print(f"Best Doc @3:        {metrics['best_doc_within_3']}/{metrics['total_questions']}")
    print(f"Best Doc @5:        {metrics['best_doc_within_5']}/{metrics['total_questions']}")
    print(f"Top1 Relevant:      {metrics['top1_relevant_rate']}% (score>=2)")
    print(f"Top3 Relevant:      {metrics['top3_relevant_rate']}%")
    print(f"Top5 Relevant:      {metrics['top5_relevant_rate']}%")
    print(f"Score Distribution: {metrics['score_distribution']}")

    out_path = "data/eval_results.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(f"\nDetails saved to {out_path}")


if __name__ == "__main__":
    main()
