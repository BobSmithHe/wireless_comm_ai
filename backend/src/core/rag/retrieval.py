"""
Hybrid retrieval pipeline: BM25 + vector search → RRF fusion → LLM reranking → context packing.
"""
from __future__ import annotations

import asyncio
import math
from collections import defaultdict

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

from .knowledge_base import RetrievedDoc


# ---------------------------------------------------------------------------
# BM25 Index
# ---------------------------------------------------------------------------


class BM25Index:
    """Sparse keyword index backed by TfidfVectorizer (BM25 approximation)."""

    def __init__(self):
        self._vectorizer = TfidfVectorizer(
            lowercase=True, max_features=10000, sublinear_tf=True,
        )
        self._matrix: np.ndarray | None = None
        self._docs: list[str] = []

    def build(self, documents: list[str]) -> None:
        self._docs = list(documents)
        if not self._docs:
            self._matrix = None
            return
        self._matrix = self._vectorizer.fit_transform(self._docs)

    def search(self, query: str, top_k: int = 20) -> list[tuple[int, float]]:
        if self._matrix is None or self._matrix.shape[0] == 0:
            return []
        q_vec = self._vectorizer.transform([query])
        scores = cosine_similarity(q_vec, self._matrix)[0]
        indices = np.argsort(scores)[::-1][:top_k]
        return [(int(i), float(scores[i])) for i in indices if scores[i] > 0]

    def add(self, text: str) -> None:
        self._docs.append(text)
        # Rebuild on next search — call build() explicitly


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------


def reciprocal_rank_fusion(
    bm25_hits: list[tuple[int, float]],
    vector_hits: list[RetrievedDoc],
    k: int = 60,
    top_k: int = 20,
) -> list[tuple[int, float]]:
    """Merge BM25 and vector rankings with RRF.

    Args:
        bm25_hits: [(doc_index, bm25_score), ...]
        vector_hits: [RetrievedDoc, ...]  (index via chunk_index)
        k: RRF constant
        top_k: number of results to return

    Returns: [(doc_index, fused_score), ...] sorted descending
    """
    scores: dict[int, float] = defaultdict(float)

    for rank, (idx, _) in enumerate(bm25_hits):
        scores[idx] += 1.0 / (k + rank + 1)

    for rank, doc in enumerate(vector_hits):
        idx = doc.chunk_index
        scores[idx] += 1.0 / (k + rank + 1)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ranked[:top_k]


# ---------------------------------------------------------------------------
# LLM Reranker
# ---------------------------------------------------------------------------


RERANK_PROMPT = """Rate how relevant each document is to the query on a scale of 1-5.
5 = directly answers the query, 1 = completely irrelevant.
Output ONLY a JSON array of integers, one per document. Example: [4, 1, 3]

Query: {query}

Documents:
{documents}

Scores:"""


async def rerank_with_llm(
    llm_client,
    query: str,
    candidates: list[tuple[int, str]],  # [(index, text), ...]
    top_k: int = 3,
) -> list[int]:
    """Use LLM to re-rank candidates. Returns indices sorted by relevance."""
    if len(candidates) <= top_k:
        return [idx for idx, _ in candidates]

    docs_text = "\n\n".join(
        f"--- Doc {i} ---\n{text[:500]}"
        for i, (idx, text) in enumerate(candidates)
    )
    prompt = RERANK_PROMPT.format(query=query, documents=docs_text)

    try:
        response = await llm_client.raw_chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=200,
        )
        scores = _parse_json_array(response)
        if len(scores) != len(candidates):
            return [idx for idx, _ in candidates[:top_k]]
        ranked = sorted(
            zip([idx for idx, _ in candidates], scores),
            key=lambda x: x[1], reverse=True,
        )
        return [idx for idx, _ in ranked[:top_k]]
    except Exception:
        return [idx for idx, _ in candidates[:top_k]]


def _parse_json_array(text: str) -> list[int]:
    import re
    text = text.strip()
    m = re.search(r"\[[\d,\s]+\]", text)
    if m:
        import json
        return json.loads(m.group())
    # Fallback: extract numbers
    return [int(x) for x in re.findall(r"\d+", text)]


# ---------------------------------------------------------------------------
# Context Packer
# ---------------------------------------------------------------------------


def pack_context(
    candidates: list[RetrievedDoc],
    budget_tokens: int = 2000,
) -> list[RetrievedDoc]:
    """Greedy token-budget packer. Keeps highest-scoring chunks that fit."""
    packed = []
    used = 0
    for doc in candidates:
        est = len(doc.content) // 4  # rough token count
        if used + est > budget_tokens and packed:
            break
        # Truncate long chunks
        if est > budget_tokens:
            max_chars = budget_tokens * 4
            doc = RetrievedDoc(
                content=doc.content[:max_chars] + "...",
                score=doc.score,
                source=doc.source,
                chunk_index=doc.chunk_index,
            )
            est = budget_tokens
        packed.append(doc)
        used += est
    return packed
