"""
Document Loader — PDF text extraction + smart chunking for knowledge base ingestion.
"""
from __future__ import annotations

import os
import re
from pathlib import Path


class DocumentLoader:
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, filepath: str, filename: str) -> list[dict]:
        """Parse a file and return a list of {text, metadata} dicts."""
        ext = os.path.splitext(filename)[1].lower()

        if ext == ".pdf":
            text, pages = self._load_pdf(filepath)
        elif ext in (".md", ".txt", ".py"):
            text = self._load_text(filepath)
            pages = None
        else:
            raise ValueError(f"Unsupported file type: {ext}")

        if not text.strip():
            return []

        chunks = self._chunk(text, source=filename, pages=pages)
        return chunks

    # ------------------------------------------------------------------
    # File readers
    # ------------------------------------------------------------------

    def _load_pdf(self, filepath: str) -> tuple[str, list[tuple[int, str]]]:
        """Extract text from a PDF, returning (full_text, [(page_num, page_text), ...])."""
        import pdfplumber

        pages: list[tuple[int, str]] = []
        full_text: list[str] = []

        with pdfplumber.open(filepath) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    pages.append((i + 1, page_text))
                    full_text.append(page_text)

        return "\n\n".join(full_text), pages

    def _load_text(self, filepath: str) -> str:
        """Read a plain-text file."""
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    def _chunk(
        self,
        text: str,
        source: str,
        pages: list[tuple[int, str]] | None = None,
    ) -> list[dict]:
        """Split text into overlapping chunks, preserving paragraph boundaries.

        If *pages* is provided, page numbers are tracked per chunk.
        """
        # Build page-aware paragraphs
        if pages:
            paragraphs: list[dict] = []
            for page_num, page_text in pages:
                for para in page_text.split("\n\n"):
                    stripped = para.strip()
                    if stripped:
                        paragraphs.append({"text": stripped, "page": page_num})
        else:
            paragraphs = [
                {"text": p.strip(), "page": 1}
                for p in text.split("\n\n")
                if p.strip()
            ]

        chunks: list[dict] = []
        current: list[str] = []
        current_len = 0
        current_pages: set[int] = set()

        for para in paragraphs:
            para_text = para["text"]
            para_len = len(para_text)

            if current_len + para_len > self.chunk_size and current:
                # Finalise current chunk
                chunk_text = "\n\n".join(current)
                chunks.append({
                    "text": chunk_text,
                    "source": source,
                    "page": sorted(current_pages),
                    "chunk_index": len(chunks),
                })

                # Start new chunk with overlap
                if self.chunk_overlap > 0:
                    overlap_text = chunk_text[-self.chunk_overlap :]
                    current = [overlap_text] if overlap_text.strip() else []
                    current_len = len(overlap_text) if overlap_text.strip() else 0
                    current_pages = set(current_pages)
                else:
                    current = []
                    current_len = 0
                    current_pages = set()

            current.append(para_text)
            current_len += para_len
            current_pages.add(para["page"])

        # Final chunk
        if current:
            chunks.append({
                "text": "\n\n".join(current),
                "source": source,
                "page": sorted(current_pages),
                "chunk_index": len(chunks),
            })

        return chunks
