"""
Conversation Memory — compressed chat history indexed into ChromaDB.
Passively injected by ChatService; NOT exposed as an Agent tool.
"""
from __future__ import annotations

import uuid
import chromadb
from chromadb.config import Settings as ChromaSettings

from ..observability import observe
from ..rag.knowledge_base import RetrievedDoc


class ConversationMemory:
    def __init__(
        self,
        persist_dir: str = "./data/chroma",
        chroma_host: str | None = None,
        chroma_port: int = 8000,
    ):
        self.persist_dir = persist_dir
        self.chroma_host = chroma_host
        self.chroma_port = chroma_port
        self._embedder = None
        self._client: chromadb.ClientAPI | None = None
        self._col: chromadb.Collection | None = None

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
            name="conversation_memory",
            metadata={"hnsw:space": "cosine"},
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        model = self._get_embedder()
        vecs = model.encode(texts, batch_size=32, show_progress_bar=False)
        return [v.tolist() for v in vecs]

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def add_chunks(self, texts: list[str], metadatas: list[dict]) -> list[str]:
        """Index compressed conversation history chunks."""
        self._ensure_client()
        ids = [uuid.uuid4().hex[:16] for _ in texts]
        embs = self._embed(texts)
        self._col.add(ids=ids, documents=texts, metadatas=metadatas, embeddings=embs)
        return ids

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    @observe(as_type="retriever")
    async def search(self, query: str, top_k: int = 5) -> list[RetrievedDoc]:
        import asyncio
        self._ensure_client()
        if self._col.count() == 0:
            return []
        model = self._get_embedder()
        q_emb = await asyncio.to_thread(model.encode, [query], show_progress_bar=False, batch_size=1)
        results = self._col.query(
            query_embeddings=[q_emb[0].tolist()],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
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
