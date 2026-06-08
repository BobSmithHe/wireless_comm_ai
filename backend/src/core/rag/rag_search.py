# rag_search.py
import copy
import json
import logging
import requests
from pymilvus import MilvusClient
from .milvus_store import _get_dense_model, COLLECTION_NAME
from ...core.config import get_settings

logger = logging.getLogger(__name__)

RRF_K = 60

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _id_fn(hit: dict) -> str:
    """Stable dedup key: parent_title_key, fallback to first 100 chars of content."""
    entity = hit.get("entity", hit)
    return entity.get("parent_title_key") or entity.get("content", "")[:100]


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
    k: int = RRF_K,
) -> list[dict]:
    dedup_a = _dedup_by_key(hits_a, _id_fn)
    dedup_b = _dedup_by_key(hits_b, _id_fn)

    scores: dict[str, float] = {}
    doc_map: dict[str, dict] = {}

    for rank, hit in enumerate(dedup_a, start=1):
        key = _id_fn(hit)
        scores[key] = scores.get(key, 0) + 1.0 / (k + rank)
        doc_map[key] = hit

    for rank, hit in enumerate(dedup_b, start=1):
        key = _id_fn(hit)
        scores[key] = scores.get(key, 0) + 1.0 / (k + rank)
        if key not in doc_map:
            doc_map[key] = hit

    sorted_keys = sorted(scores, key=scores.get, reverse=True)
    merged = []
    for key in sorted_keys:
        hit = copy.deepcopy(doc_map[key])
        hit["rrf_score"] = scores[key]
        merged.append(hit)
    return merged


# ---------------------------------------------------------------------------
# retrieval primitives
# ---------------------------------------------------------------------------

def search_dense(client: MilvusClient, query: str, topk: int = 30):
    q_dense = _get_dense_model().encode(query).tolist()
    res = client.search(
        collection_name=COLLECTION_NAME,
        data=[q_dense],
        anns_field="dense_vec",
        limit=topk,
        search_params={"metric_type": "L2", "params": {"nprobe": 10}},
        output_fields=["content", "meta_json", "parent_title_key", "doc_source"],
    )
    return res[0] if res else []


def search_sparse(client: MilvusClient, query: str, topk: int = 30):
    res = client.search(
        collection_name=COLLECTION_NAME,
        data=[query],
        anns_field="sparse_vec",
        limit=topk,
        search_params={"metric_type": "BM25"},
        output_fields=["content", "meta_json", "parent_title_key", "doc_source"],
    )
    return res[0] if res else []


def search_hybrid(client: MilvusClient, query: str, topk: int = 30) -> list[dict]:
    dense_hits = search_dense(client, query, topk)
    sparse_hits = search_sparse(client, query, topk)
    merged = _rrf_merge(dense_hits, sparse_hits)
    return merged[:topk]


# ---------------------------------------------------------------------------
# LLM rerank (ZhipuAI)
# ---------------------------------------------------------------------------

def llm_rerank(query: str, hits: list[dict], top_k: int = 30) -> list[dict]:
    candidates = hits[:top_k]
    if len(candidates) <= 1:
        for h in candidates:
            h["llm_score"] = None
        return candidates

    documents = [h["entity"].get("content", "")[:2000] for h in candidates]

    s = get_settings()
    if not s.zhipu_api_key or not s.zhipu_rerank_url:
        for h in candidates:
            h["llm_score"] = None
        return candidates

    try:
        resp = requests.post(
            s.zhipu_rerank_url,
            json={
                "model": s.zhipu_rerank_model,
                "query": query,
                "documents": documents,
                "top_n": len(candidates),
            },
            headers={
                "Authorization": f"Bearer {s.zhipu_api_key}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
    except Exception as e:
        logger.warning("ZhipuAI rerank call failed: %s", e)
        for h in candidates:
            h["llm_score"] = None
        return candidates

    results = result.get("results", [])

    reranked = []
    n = len(candidates)
    for r in sorted(results, key=lambda x: x.get("relevance_score", 0), reverse=True):
        idx = r.get("index", 0)
        if 0 <= idx < n:
            candidates[idx]["llm_score"] = r.get("relevance_score", 0)
            reranked.append(candidates[idx])

    for c in candidates:
        if c not in reranked:
            c["llm_score"] = None
            reranked.append(c)
    return reranked


# ---------------------------------------------------------------------------
# unified entry point
# ---------------------------------------------------------------------------

def rag_search(
    client: MilvusClient,
    query: str,
    retrieve_k: int = 30,
    final_k: int = 8,
    rerank: bool = True,
) -> list[dict]:
    """Unified hybrid search with optional LLM rerank."""
    hits = search_hybrid(client, query, topk=retrieve_k)
    if rerank:
        hits = llm_rerank(query, hits, top_k=retrieve_k)
    return hits[:final_k]


# ---------------------------------------------------------------------------
# full-section retrieval by title path
# ---------------------------------------------------------------------------

def get_full_by_title_path(client: MilvusClient, title_path: str) -> str:
    """Retrieve full content for a section using parent_title_key prefix match.
    Uses boundary-aware matching to avoid false positives (e.g. 9.4 vs 19.4)."""
    import re
    # Find the LAST (most specific) section number
    numbers = re.findall(r"(\d+(?:\.\d+)*)", title_path)
    section = numbers[-1] if numbers else None
    if section:
        # Boundary match: section followed by non-digit or end-of-string
        expr = f'parent_title_key like "%{section}%"'
        rows = client.query(
            collection_name=COLLECTION_NAME,
            filter=expr,
            output_fields=["content", "meta_json"],
            limit=9999,
        )
        # Filter client-side to avoid false positives like "19.4" matching "9.4"
        def _match(row):
            key = json.loads(row["meta_json"]).get("parent_title_key", "")
            parts = key.split(">")
            return any(p == section or p.startswith(section + ".") or p.startswith(section + " ") for p in parts)
        rows = [r for r in rows if _match(r)]
    else:
        escaped = title_path.replace('"', '\\"')
        expr = f'parent_title_key == "{escaped}"'
        rows = client.query(
            collection_name=COLLECTION_NAME,
            filter=expr,
            output_fields=["content", "meta_json"],
            limit=9999,
        )

    if not rows:
        return ""

    def sort_func(x):
        m = json.loads(x["meta_json"])
        return m.get("sub_chunk", 1)

    rows_sort = sorted(rows, key=sort_func)
    return "\n\n".join([i["content"] for i in rows_sort])
