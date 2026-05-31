"""
Retrieval and generation evaluation metrics.
"""
import math
from statistics import mean


def recall_at_k(relevant: set[str], retrieved: list[str], k: int) -> float:
    """Proportion of relevant docs found in top-k retrieved."""
    if not relevant:
        return 1.0
    found = relevant & set(retrieved[:k])
    return len(found) / len(relevant)


def precision_at_k(relevant: set[str], retrieved: list[str], k: int) -> float:
    """Proportion of top-k retrieved that are relevant."""
    top = retrieved[:k]
    if not top:
        return 0.0
    return len(relevant & set(top)) / len(top)


def mrr(relevant: set[str], retrieved: list[str]) -> float:
    """Mean reciprocal rank — 1 / rank of first relevant doc."""
    for i, doc in enumerate(retrieved):
        if doc in relevant:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(relevant: set[str], retrieved: list[str], k: int) -> float:
    """Normalized discounted cumulative gain at k."""
    # Deduplicate: only count first occurrence of each relevant doc
    seen: set[str] = set()
    dcg = 0.0
    for i, doc in enumerate(retrieved[:k]):
        if doc in relevant and doc not in seen:
            dcg += 1.0 / math.log2(i + 2)
            seen.add(doc)

    ideal_count = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_count))

    return min(dcg / idcg, 1.0) if idcg > 0 else 0.0


# ---------------------------------------------------------------------------
# LLM-as-judge generation metrics
# ---------------------------------------------------------------------------

JUDGE_PROMPT_FAITHFULNESS = """You are evaluating an AI answer.

Question: {query}
Context used: {context}
Answer: {answer}

Is the answer fully supported by the context above?
Does it contain ANY information not present in the context?
Answer ONLY "yes" (fully faithful) or "no" (contains hallucinations).
"""

JUDGE_PROMPT_FACT_COVERAGE = """You are checking if an answer covers expected facts.

Question: {query}
Answer: {answer}
Expected facts that SHOULD be mentioned: {facts}

For each fact, output YES or NO. Then give a coverage score (0-100).
Format: SCORE: <number>
"""


async def evaluate_faithfulness(
    llm_client, query: str, context: str, answer: str,
) -> bool:
    """LLM-as-judge: is the answer faithful to the retrieved context?"""
    prompt = JUDGE_PROMPT_FAITHFULNESS.format(
        query=query, context=context[:3000], answer=answer[:1000],
    )
    try:
        response = await llm_client.raw_chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=50,
        )
        return "yes" in response.lower() and "no" not in response.lower().replace(
            "yes", ""
        ).replace("not", "")
    except Exception:
        return False


async def evaluate_fact_coverage(
    llm_client, query: str, answer: str, facts: list[str],
) -> float:
    """LLM-as-judge: what percentage of expected facts are covered?"""
    prompt = JUDGE_PROMPT_FACT_COVERAGE.format(
        query=query, answer=answer[:1500], facts=", ".join(facts),
    )
    try:
        response = await llm_client.raw_chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=200,
        )
        import re
        m = re.search(r"SCORE:\s*(\d+)", response, re.IGNORECASE)
        if m:
            return int(m.group(1)) / 100.0
        # Count YES mentions
        yes_count = sum(1 for line in response.split("\n") if "YES" in line.upper())
        return yes_count / max(len(facts), 1)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Aggregate report
# ---------------------------------------------------------------------------


def build_report(name: str, retrieval_metrics: dict, gen_metrics: dict) -> dict:
    return {
        "name": name,
        "retrieval": retrieval_metrics,
        "generation": gen_metrics,
    }


def format_report(report: dict) -> str:
    """Human-readable markdown report."""
    lines = [f"## {report['name']}", ""]
    r = report["retrieval"]
    if r:
        lines.append("### Retrieval")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        for k, v in r.items():
            lines.append(f"| {k} | {v:.4f} |")
        lines.append("")
    g = report["generation"]
    if g:
        lines.append("### Generation")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        for k, v in g.items():
            lines.append(f"| {k} | {v:.4f} |")
    return "\n".join(lines)
