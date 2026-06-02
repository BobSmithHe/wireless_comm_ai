# rag_search.py
import json
import logging
import requests
from pymilvus import MilvusClient
from .milvus_store import _get_dense_model, COLLECTION_NAME

# Rerank defaults (not used by default — KnowledgeBase handles reranking)
ZHIPU_API_KEY = "0d9b8fb9184241d091a83d01e61ac394.K0f8fpyIKH2LVmHW"
ZHIPU_RERANK_URL = "https://open.bigmodel.cn/api/paas/v4/rerank"
ZHIPU_RERANK_MODEL = "rerank"

logger = logging.getLogger(__name__)

RRF_K = 60


def _dedup_by_key(hits: list[dict], id_fn: callable) -> list[dict]:
    seen: dict[str, dict] = {}
    deduped: list[dict] = []
    for h in hits:
        key = id_fn(h)
        if key not in seen:
            seen[key] = h
            deduped.append(h)
    return deduped


def _rrf_merge(
    hits_a: list[dict],
    hits_b: list[dict],
    id_fn: callable = lambda h: h["entity"].get("parent_title_key", ""),
    k: int = RRF_K,
) -> list[dict]:
    dedup_a = _dedup_by_key(hits_a, id_fn)
    dedup_b = _dedup_by_key(hits_b, id_fn)

    scores: dict[str, float] = {}
    doc_map: dict[str, dict] = {}

    for rank, hit in enumerate(dedup_a, start=1):
        key = id_fn(hit)
        scores[key] = scores.get(key, 0) + 1.0 / (k + rank)
        doc_map[key] = hit

    for rank, hit in enumerate(dedup_b, start=1):
        key = id_fn(hit)
        scores[key] = scores.get(key, 0) + 1.0 / (k + rank)
        if key not in doc_map:
            doc_map[key] = hit

    sorted_keys = sorted(scores, key=scores.get, reverse=True)
    merged = []
    for key in sorted_keys:
        hit = doc_map[key]
        hit["rrf_score"] = scores[key]
        merged.append(hit)
    return merged


def search_dense(client: MilvusClient, query: str, topk: int = 10):
    q_dense = _get_dense_model().encode(query).tolist()
    res = client.search(
        collection_name=COLLECTION_NAME,
        data=[q_dense],
        anns_field="dense_vec",
        limit=topk,
        search_params={"metric_type": "L2", "params": {"nprobe": 10}},
        output_fields=["content", "meta_json", "parent_title_key"],
    )
    return res[0] if res else []


def search_sparse(client: MilvusClient, query: str, topk: int = 10):
    res = client.search(
        collection_name=COLLECTION_NAME,
        data=[query],
        anns_field="sparse_vec",
        limit=topk,
        search_params={"metric_type": "BM25"},
        output_fields=["content", "meta_json", "parent_title_key"],
    )
    return res[0] if res else []


def search_hybrid(client: MilvusClient, query: str, topk: int = 10):
    dense_hits = search_dense(client, query, topk)
    sparse_hits = search_sparse(client, query, topk)
    merged = _rrf_merge(dense_hits, sparse_hits)
    return merged[:topk]


def llm_rerank(query: str, hits: list[dict], top_k: int = 10) -> list[dict]:
    """Re-rank RRF-merged results using ZhipuAI native rerank API.

    Returns re-ordered hits with added ``llm_score`` field (1.0 = best, 0.0 = worst).
    """
    candidates = hits[:top_k]
    if len(candidates) <= 1:
        for h in candidates:
            h["llm_score"] = 1.0
        return candidates

    documents = [h["entity"].get("content", "")[:2000] for h in candidates]

    if not ZHIPU_API_KEY or not ZHIPU_RERANK_URL:
        for h in candidates:
            h["llm_score"] = 1.0
        return candidates

    try:
        resp = requests.post(
            ZHIPU_RERANK_URL,
            json={
                "model": ZHIPU_RERANK_MODEL,
                "query": query,
                "documents": documents,
                "top_n": len(candidates),
            },
            headers={
                "Authorization": f"Bearer {ZHIPU_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
    except Exception as e:
        logger.warning("ZhipuAI rerank call failed: %s", e)
        for h in candidates:
            h["llm_score"] = 1.0
        return candidates

    # response format: {"results": [{"index": 2, "relevance_score": 0.99999}, ...]}
    # note: ZhipuAI rerank outputs scores in a very narrow range (~0.99999x).
    # normalize to 0-1 so scores are human-readable.
    results = result.get("results", [])
    raw_scores = [r.get("relevance_score", 0) for r in results]
    min_s = min(raw_scores) if raw_scores else 0
    max_s = max(raw_scores) if raw_scores else 1
    score_range = max_s - min_s

    reranked = []
    n = len(candidates)
    for r in sorted(results, key=lambda x: x.get("relevance_score", 0), reverse=True):
        idx = r.get("index", 0)
        if 0 <= idx < n:
            raw = r.get("relevance_score", 0)
            normalized = (raw - min_s) / score_range if score_range > 0 else 0.5
            candidates[idx]["llm_score"] = round(normalized, 4)
            reranked.append(candidates[idx])
    for i, c in enumerate(candidates):
        if c not in reranked:
            c["llm_score"] = 0.0
            reranked.append(c)
    return reranked


def get_full_by_title_path(client: MilvusClient, title_path: str):
    # Use regex pattern to match all child sections under the same parent heading
    import re
    # Extract section numbers like "9.4" from the title path
    m = re.search(r"(\d+\.\d+)", title_path)
    if m:
        pattern = m.group(1)  # e.g. "9.4"
        # Match all keys containing this section number
        expr = f'parent_title_key like "%{pattern}%"'
    else:
        # Fallback: exact match
        escaped = title_path.replace('"', '\\\\"')
        expr = f'parent_title_key == "{escaped}"'

    rows = client.query(
        collection_name=COLLECTION_NAME,
        filter=expr,
        output_fields=["content", "meta_json"],
        limit=9999,
    )

    def sort_func(x):
        m = json.loads(x["meta_json"])
        return m.get("sub_chunk", 1)

    rows_sort = sorted(rows, key=sort_func)
    full_md = "\n\n".join([i["content"] for i in rows_sort])
    return full_md
