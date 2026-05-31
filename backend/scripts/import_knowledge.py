"""
Import knowledge base documents into ChromaDB.
Reads .md and .pdf files from data/knowledge_base/ and indexes them.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.rag.knowledge_base import KnowledgeBase


def import_documents():
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge_base")
    kb = KnowledgeBase()

    count = 0
    for root, dirs, files in os.walk(data_dir):
        for fname in files:
            if fname.endswith((".md", ".txt")):
                filepath = os.path.join(root, fname)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                # Split into chunks by double newline
                chunks = [c.strip() for c in content.split("\n\n") if c.strip()]
                for i, chunk in enumerate(chunks):
                    kb.add_document(
                        text=chunk,
                        metadata={
                            "source": fname,
                            "category": os.path.basename(root),
                            "chunk_index": i,
                        },
                    )
                    count += 1
                    if count % 20 == 0:
                        print(f"  Imported {count} chunks...")

    print(f"Knowledge base import complete. Total chunks: {count}")


if __name__ == "__main__":
    import_documents()
