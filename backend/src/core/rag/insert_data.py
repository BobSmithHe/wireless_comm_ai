"""
Standalone data insertion script — preload knowledge_base docs into Milvus.
Usage: python -m src.core.rag.insert_data
"""
import os, sys, json, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("insert_data")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "knowledge_base")


def main():
    from pymilvus import MilvusClient
    from .md_splitter import SmartMarkdownSplitter
    from .milvus_store import init_collection, insert_chunks, COLLECTION_NAME

    # Milvus connection from env
    uri = os.environ.get("MILVUS_URI", "http://localhost:19530")
    token = os.environ.get("MILVUS_TOKEN", "")
    db_name = os.environ.get("MILVUS_DB_NAME", "")

    kwargs = {"uri": uri}
    if token:
        kwargs["token"] = token
    if db_name:
        kwargs["db_name"] = db_name

    client = MilvusClient(**kwargs)
    logger.info("Connected to Milvus at %s", uri)

    init_collection(client)

    splitter = SmartMarkdownSplitter(chunk_size=800, chunk_overlap=150, max_chunk_size=1800)

    # Walk knowledge_base directory
    data_dir = os.path.abspath(DATA_DIR)
    if not os.path.isdir(data_dir):
        logger.error("Knowledge base directory not found: %s", data_dir)
        sys.exit(1)

    total = 0
    for root, dirs, files in os.walk(data_dir):
        for fname in files:
            if not fname.endswith((".md", ".txt")):
                continue
            filepath = os.path.join(root, fname)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            if not content.strip():
                continue

            chunks = splitter.split_text(content)
            for ck in chunks:
                ck.metadata["doc_source"] = fname
                ck.metadata["category"] = os.path.basename(root)

            insert_chunks(client, chunks, fname)
            logger.info("  %s: %d chunks", fname, len(chunks))
            total += len(chunks)

    logger.info("Done. Total %d chunks indexed into Milvus collection '%s'", total, COLLECTION_NAME)


if __name__ == "__main__":
    main()
