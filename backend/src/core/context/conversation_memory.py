"""Conversation Memory — compressed conversation history indexed into Milvus."""
from __future__ import annotations

from pymilvus import MilvusClient

from ..observability import observe
from ..rag.knowledge_base import RetrievedDoc
from .milvus_memory import (
    COLLECTION_NAME, init_collection, insert_memories, delete_by_source, search_memories,
)


class ConversationMemory:
    def __init__(self, milvus_uri: str = "http://localhost:19530",
                 milvus_token: str = "", milvus_db_name: str = ""):
        kwargs = {"uri": milvus_uri}
        if milvus_token:
            kwargs["token"] = milvus_token
        if milvus_db_name:
            kwargs["db_name"] = milvus_db_name
        self._client = MilvusClient(**kwargs)
        self._ready = False

    def _ensure_ready(self):
        if not self._ready:
            init_collection(self._client)
            self._ready = True

    def add_chunks(self, texts: list[str], metadatas: list[dict]) -> list[int]:
        """Insert memory chunks, replacing old entries for same source_tag first."""
        self._ensure_ready()
        # Delete old entries for same source before inserting new ones
        for meta in metadatas:
            tag = meta.get("source", "")
            if tag:
                delete_by_source(self._client, tag)
        return insert_memories(self._client, texts, metadatas)

    @observe(as_type="retriever")
    async def search(self, query: str, user_id: int = 0, top_k: int = 5) -> list[RetrievedDoc]:
        """Search compressed memories scoped to user."""
        self._ensure_ready()
        if self._client.get_collection_stats(COLLECTION_NAME)["row_count"] == 0:
            return []

        from .milvus_memory import _get_embedder
        import asyncio
        model = _get_embedder()
        q_vec = await asyncio.to_thread(
            model.encode, [query], show_progress_bar=False, batch_size=1,
        )
        results = self._client.search(
            collection_name=COLLECTION_NAME,
            data=[q_vec[0].tolist()],
            anns_field="dense_vec",
            limit=top_k * 3,
            search_params={"metric_type": "L2", "params": {"nprobe": 10}},
            output_fields=["content", "source_tag", "conversation_id"],
            filter=f"user_id == {user_id}",
        )
        hits = results[0] if results else []

        seen = set()
        docs = []
        for h in hits:
            entity = h.get("entity", h)
            content = entity.get("content", "")
            key = content[:100]
            if key in seen:
                continue
            seen.add(key)
            distance = h.get("distance", 1.0)
            score = round(1.0 - distance / 2.0, 4)
            meta = {
                "source": entity.get("source_tag", ""),
                "conversation_id": entity.get("conversation_id", 0),
            }
            docs.append(RetrievedDoc(
                content=content,
                score=max(0.0, min(1.0, score)),
                source=meta.get("source", ""),
            ))
        return docs[:top_k]
