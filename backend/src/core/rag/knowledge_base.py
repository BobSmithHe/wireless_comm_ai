"""
Knowledge Base — wraps SmartMarkdownSplitter + Milvus hybrid search.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from pymilvus import MilvusClient

from .md_splitter import SmartMarkdownSplitter
from .milvus_store import init_collection, insert_chunks, COLLECTION_NAME
from .rag_search import search_dense, search_sparse, search_hybrid, llm_rerank, get_full_by_title_path
from ..observability import observe


@dataclass
class RetrievedDoc:
    content: str
    score: float
    source: str = ""
    chunk_index: int = 0


class KnowledgeBase:
    def __init__(
        self,
        *,
        llm_client=None,
        milvus_uri: str = "./data/milvus.db",
        milvus_token: str = "",
        milvus_db_name: str = "",
        embedding_model: str = "BAAI/bge-large-zh-v1.5",
        embedding_dimension: int = 1024,
        embedding_device: str = "cpu",
    ):
        self.llm = llm_client
        self.milvus_uri = milvus_uri
        self.milvus_token = milvus_token
        self.milvus_db_name = milvus_db_name
        self.embedding_model = embedding_model
        self.embedding_dimension = embedding_dimension
        self.embedding_device = embedding_device
        self._client: MilvusClient | None = None
        self._ready = False
        self._splitter = SmartMarkdownSplitter(
            chunk_size=800, chunk_overlap=150, max_chunk_size=1800,
        )

    def _get_client(self) -> MilvusClient:
        if self._client is None:
            kwargs = {"uri": self.milvus_uri}
            if self.milvus_token:
                kwargs["token"] = self.milvus_token
            if self.milvus_db_name:
                kwargs["db_name"] = self.milvus_db_name
            self._client = MilvusClient(**kwargs)
        return self._client

    def _ensure_collection(self):
        if self._ready:
            return
        init_collection(self._get_client())
        self._ready = True

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add_document(self, text: str, metadata: dict | None = None) -> str:
        return self.add_documents([text], [metadata or {}])[0]

    def add_documents(self, texts: list[str], metadatas: list[dict] | None = None) -> list[str]:
        self._ensure_collection()
        metas = metadatas if metadatas else [{}] * len(texts)
        ids = []
        for i, text in enumerate(texts):
            chunks = self._splitter.split_text(text)
            src = metas[i].get("source", f"doc_{uuid.uuid4().hex[:8]}")
            for ck in chunks:
                ck.metadata["doc_source"] = src
                ck.metadata["category"] = metas[i].get("category", "")
                ck.metadata.setdefault("parent_title_key", "")
            if chunks:
                insert_chunks(self._get_client(), chunks, src)
                ids.extend([ck.chunk_id for ck in chunks])
        return ids

    # ------------------------------------------------------------------
    # Search
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
        self._ensure_collection()
        client = self._get_client()
        stats = client.get_collection_stats(COLLECTION_NAME)
        if stats["row_count"] == 0:
            return []

        n_candidates = max(top_k * 4, 20)

        if mode == "vector":
            hits = search_dense(client, query, topk=top_k)
        elif mode == "bm25":
            hits = search_sparse(client, query, topk=top_k)
        else:
            hits = search_hybrid(client, query, topk=n_candidates)
            if rerank and len(hits) > top_k:
                hits = llm_rerank(query, hits, min(len(hits), n_candidates))
            hits = hits[:top_k]

        expanded: list[RetrievedDoc] = []
        seen_titles: set[str] = set()
        for h in hits:
            entity = h.get("entity", h)
            title_key = entity.get("parent_title_key", "")
            content = entity.get("content", "")
            doc_source = entity.get("doc_source", "")
            score = h.get("llm_score", h.get("rrf_score", h.get("distance", 0)))

            if not title_key:
                if content:
                    expanded.append(RetrievedDoc(content=content, score=round(score, 4), source=doc_source))
                continue

            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            full_text = get_full_by_title_path(client, title_key)
            expanded.append(RetrievedDoc(
                content=full_text,
                score=round(score, 4) if isinstance(score, (int, float)) else 0.6,
                source=doc_source,
            ))

        return expanded

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    def list_documents(self) -> list[dict]:
        self._ensure_collection()
        results = self._get_client().query(
            collection_name=COLLECTION_NAME, filter="",
            output_fields=["doc_source"], limit=50000,
        )
        seen: dict[str, int] = {}
        for r in results:
            src = r.get("doc_source", "")
            if src:
                seen[src] = seen.get(src, 0) + 1
        return [{"source": s, "chunks": c} for s, c in seen.items()]

    def remove_document(self, source: str) -> int:
        self._ensure_collection()
        client = self._get_client()
        before = client.get_collection_stats(COLLECTION_NAME)["row_count"]
        client.delete(collection_name=COLLECTION_NAME, filter=f'doc_source == "{source}"')
        return before - client.get_collection_stats(COLLECTION_NAME)["row_count"]

    def clear(self) -> None:
        self._ready = False

    def __len__(self) -> int:
        self._ensure_collection()
        return self._get_client().get_collection_stats(COLLECTION_NAME)["row_count"]
