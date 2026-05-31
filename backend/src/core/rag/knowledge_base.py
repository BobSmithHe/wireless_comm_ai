"""
Knowledge Base — hybrid retrieval (BM25 + vector → RRF → LLM rerank → pack).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import chromadb
from chromadb.config import Settings as ChromaSettings

from ..observability import observe
from ...config.settings import get_settings as _get_settings


@dataclass
class RetrievedDoc:
    content: str
    score: float
    source: str = ""
    chunk_index: int = 0


class KnowledgeBase:
    def __init__(
        self,
        llm_client=None,
        persist_dir: str = "./data/chroma",
        chroma_host: str | None = None,
        chroma_port: int = 8000,
    ):
        self.persist_dir = persist_dir
        self.chroma_host = chroma_host
        self.chroma_port = chroma_port
        self.llm = llm_client
        self._embedder = None
        self._client: chromadb.ClientAPI | None = None
        self._col: chromadb.Collection | None = None
        self._bm25_ready = False

    def _get_embedder(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
        return self._embedder

    def _ensure_client(self):
        if self._client is not None:
            return
        if self.chroma_host:
            self._client = chromadb.HttpClient(
                host=self.chroma_host, port=self.chroma_port,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        else:
            self._client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        self._col = self._client.get_or_create_collection(
            name="knowledge_base",
            metadata={"hnsw:space": "cosine"},
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        model = self._get_embedder()
        vecs = model.encode(texts, batch_size=32, show_progress_bar=False)
        return [v.tolist() for v in vecs]

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add_document(self, text: str, metadata: dict | None = None) -> str:
        self._ensure_client()
        doc_id = uuid.uuid4().hex[:16]
        emb = self._embed([text])
        self._col.add(ids=[doc_id], documents=[text], metadatas=[metadata or {}], embeddings=emb)
        self._bm25_ready = False
        return doc_id

    def add_documents(self, texts: list[str], metadatas: list[dict] | None = None) -> list[str]:
        self._ensure_client()
        ids = [uuid.uuid4().hex[:16] for _ in texts]
        metas = metadatas if metadatas else [{}] * len(texts)
        embs = self._embed(texts)
        self._col.add(ids=ids, documents=texts, metadatas=metas, embeddings=embs)
        self._bm25_ready = False
        return ids

    # ------------------------------------------------------------------
    # Hybrid search
    # ------------------------------------------------------------------

    @observe(as_type="retriever")
    async def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict | None = None,
        mode: str = "hybrid",
        rerank: bool = True,
        context_budget: int | None = None,
    ) -> list[RetrievedDoc]:
        """Hybrid retrieval: BM25 + vector → RRF → LLM rerank → context pack.

        Args:
            query: search query
            top_k: number of final results
            filters: ChromaDB metadata filter, e.g. {'category': 'algorithms'}
            mode: 'hybrid' | 'vector' | 'bm25'
            rerank: whether to use LLM reranking
            context_budget: max tokens for packed context (None → no packing)
        """
        import asyncio
        from .retrieval import (
            BM25Index, reciprocal_rank_fusion, rerank_with_llm, pack_context,
        )

        self._ensure_client()
        if self._col.count() == 0:
            return []

        settings = _get_settings()
        if context_budget is None:
            context_budget = getattr(settings, 'kb_context_budget_tokens', 2000)

        # Build where clause for ChromaDB
        where = filters or None

        # --- Vector search ---
        model = self._get_embedder()
        q_emb = await asyncio.to_thread(model.encode, [query], show_progress_bar=False, batch_size=1)

        n_candidates = max(top_k * 4, 20)
        results = self._col.query(
            query_embeddings=[q_emb[0].tolist()],
            n_results=n_candidates,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        vector_hits = self._parse_results(results)

        if mode == "vector":
            final = vector_hits[:top_k]
            if context_budget:
                final = pack_context(final, context_budget)
            return final

        # --- BM25 search ---
        all_docs = self._col.get(include=["documents", "metadatas"])
        all_texts = all_docs["documents"] or []
        bm25 = BM25Index()
        bm25.build(all_texts)
        bm25_hits = bm25.search(query, top_k=n_candidates)
        bm25_scored: list[tuple[int, float]] = [(i, s) for i, s in bm25_hits]

        if mode == "bm25":
            final = []
            for idx, score in bm25_scored[:top_k]:
                meta = (all_docs["metadatas"] or [{}])[idx] if idx < len(all_docs["metadatas"] or []) else {}
                final.append(RetrievedDoc(
                    content=all_texts[idx],
                    score=round(score, 4),
                    source=meta.get("source", ""),
                    chunk_index=idx,
                ))
            if context_budget:
                final = pack_context(final, context_budget)
            return final

        # --- Hybrid: RRF fusion ---
        fused = reciprocal_rank_fusion(bm25_scored, vector_hits, top_k=n_candidates)
        candidates: list[RetrievedDoc] = []
        for idx, score in fused:
            if idx < len(all_texts):
                meta = (all_docs["metadatas"] or [{}])[idx] if idx < len(all_docs["metadatas"] or []) else {}
                candidates.append(RetrievedDoc(
                    content=all_texts[idx],
                    score=round(score, 4),
                    source=meta.get("source", ""),
                    chunk_index=idx,
                ))

        # --- LLM Rerank ---
        if rerank and self.llm and len(candidates) > top_k:
            llm_candidates = [(d.chunk_index, d.content) for d in candidates]
            kept = await rerank_with_llm(self.llm, query, llm_candidates, top_k=top_k * 2)
            keep_set = set(kept)
            candidates = [d for d in candidates if d.chunk_index in keep_set]

        # --- Context pack ---
        if context_budget:
            candidates = pack_context(candidates, context_budget)

        return candidates[:top_k]

    # ------------------------------------------------------------------
    # Document management
    # ------------------------------------------------------------------

    def list_documents(self) -> list[dict]:
        self._ensure_client()
        if self._col.count() == 0:
            return []
        all_meta = self._col.get(include=["metadatas"])
        seen: dict[str, dict] = {}
        for meta in (all_meta["metadatas"] or []):
            if not meta:
                continue
            source = meta.get("source", "")
            if not source:
                continue
            page = meta.get("page", [])
            if isinstance(page, int):
                page = [page]
            if source not in seen:
                seen[source] = {"chunk_count": 1, "pages": set(page)}
            else:
                seen[source]["chunk_count"] += 1
                seen[source]["pages"].update(page)
        return [
            {"source": s, "chunks": info["chunk_count"], "pages": sorted(info["pages"]) if info["pages"] else []}
            for s, info in seen.items()
        ]

    def remove_document(self, source: str) -> int:
        self._ensure_client()
        before = self._col.count()
        self._col.delete(where={"source": source})
        return before - self._col.count()

    def clear(self) -> None:
        self._ensure_client()
        self._client.delete_collection("knowledge_base")
        self._col = self._client.get_or_create_collection(
            name="knowledge_base", metadata={"hnsw:space": "cosine"},
        )

    def __len__(self) -> int:
        self._ensure_client()
        return self._col.count()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_results(results: dict) -> list[RetrievedDoc]:
        docs = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                distance = results["distances"][0][i]
                score = 1.0 - (distance / 2.0)
                meta = results["metadatas"][0][i] or {}
                docs.append(RetrievedDoc(
                    content=results["documents"][0][i] or "",
                    score=round(max(0.0, min(1.0, score)), 4),
                    source=meta.get("source", ""),
                    chunk_index=meta.get("chunk_index", 0),
                ))
        return docs
