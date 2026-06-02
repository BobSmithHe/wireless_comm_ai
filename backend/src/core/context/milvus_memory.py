"""Conversation memory stored in Milvus — partitioned by user & conversation."""
import json
import logging
from pymilvus import MilvusClient, DataType, FieldSchema, CollectionSchema
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

COLLECTION_NAME = "conversation_memory"
_embedder = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder


def init_collection(client: MilvusClient) -> None:
    if client.has_collection(COLLECTION_NAME):
        client.load_collection(COLLECTION_NAME)
        logger.info("memory collection %s loaded", COLLECTION_NAME)
        return

    fields = [
        FieldSchema("id", DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema("dense_vec", DataType.FLOAT_VECTOR, dim=384),
        FieldSchema("content", DataType.VARCHAR, max_length=65535),
        FieldSchema("user_id", DataType.INT64),
        FieldSchema("conversation_id", DataType.INT64),
        FieldSchema("source_tag", DataType.VARCHAR, max_length=128),
    ]
    schema = CollectionSchema(fields, description="compressed conversation memory")
    client.create_collection(collection_name=COLLECTION_NAME, schema=schema)

    idx = client.prepare_index_params()
    idx.add_index(field_name="dense_vec", index_type="IVF_FLAT", metric_type="L2", params={"nlist": 64})
    idx.add_index(field_name="user_id", index_type="AUTOINDEX")
    idx.add_index(field_name="conversation_id", index_type="AUTOINDEX")
    client.create_index(collection_name=COLLECTION_NAME, index_params=idx)
    client.load_collection(COLLECTION_NAME)
    logger.info("memory collection %s created", COLLECTION_NAME)


def insert_memories(client: MilvusClient, texts: list[str], metadatas: list[dict]) -> list[int]:
    """Insert compressed memory chunks. Returns auto-generated IDs."""
    model = _get_embedder()
    vecs = model.encode(texts, batch_size=32, show_progress_bar=False)
    rows = []
    for i, text in enumerate(texts):
        meta = metadatas[i] if i < len(metadatas) else {}
        rows.append({
            "dense_vec": vecs[i].tolist(),
            "content": text,
            "user_id": meta.get("user_id", 0),
            "conversation_id": meta.get("conversation_id", 0),
            "source_tag": meta.get("source", ""),
        })
    result = client.insert(collection_name=COLLECTION_NAME, data=rows)
    client.flush(collection_name=COLLECTION_NAME)
    return result.get("ids", [])


def delete_by_source(client: MilvusClient, source_tag: str) -> int:
    """Delete all entries with the given source_tag. Returns count deleted."""
    before = client.get_collection_stats(COLLECTION_NAME)["row_count"]
    client.delete(collection_name=COLLECTION_NAME, filter=f'source_tag == "{source_tag}"')
    return before - client.get_collection_stats(COLLECTION_NAME)["row_count"]


def search_memories(
    client: MilvusClient,
    query: str,
    user_id: int,
    conversation_id: int | None = None,
    top_k: int = 5,
) -> list[dict]:
    """Search conversation memory, scoped to user. Results include score, content, source_tag."""
    if client.get_collection_stats(COLLECTION_NAME)["row_count"] == 0:
        return []

    model = _get_embedder()
    q_vec = model.encode([query], show_progress_bar=False)[0].tolist()

    expr = f"user_id == {user_id}"
    results = client.search(
        collection_name=COLLECTION_NAME,
        data=[q_vec],
        anns_field="dense_vec",
        limit=top_k * 2,
        search_params={"metric_type": "L2", "params": {"nprobe": 10}},
        output_fields=["content", "source_tag", "conversation_id"],
        filter=expr,
    )

    hits = results[0] if results else []
    seen = set()
    out = []
    for h in hits:
        entity = h.get("entity", h)
        content = entity.get("content", "")
        # Deduplicate identical content
        key = content[:100]
        if key in seen:
            continue
        seen.add(key)
        distance = h.get("distance", 1.0)
        out.append({
            "content": content,
            "score": round(1.0 - distance / 2.0, 4),
            "source_tag": entity.get("source_tag", ""),
            "conversation_id": entity.get("conversation_id", 0),
        })
    return out[:top_k]
