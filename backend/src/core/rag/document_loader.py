"""
Document Loader — PDF text extraction + smart chunking for knowledge base ingestion.
"""
from __future__ import annotations

import os
import re


class DocumentLoader:
    HARD_MAX = 5000

    def __init__(self, chunk_size: int = 2000, chunk_overlap: int = 400):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def load(self, filepath: str, filename: str) -> list[dict]:
        ext = os.path.splitext(filename)[1].lower()
        if ext == ".pdf":
            text, pages = self._load_pdf(filepath)
            if not text.strip():
                return []
            return self._chunk(text, source=filename, pages=pages)
        elif ext in (".md", ".txt", ".py"):
            text = self._load_text(filepath)
            if not text.strip():
                return []
            return self._chunk_markdown(text, source=filename)
        else:
            raise ValueError(f"Unsupported file type: {ext}")

    def _load_pdf(self, filepath: str) -> tuple[str, list[tuple[int, str]]]:
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
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()

    def _chunk_markdown(self, text: str, source: str) -> list[dict]:
        sections = re.split(r"\n(?=#\s)", text)
        chunks: list[dict] = []
        buffer = ""
        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue
            if len(sec) < 300 and buffer:
                buffer += "\n\n" + sec
                continue
            if buffer:
                chunks.append({"text": buffer, "source": source, "chunk_index": len(chunks)})
                buffer = ""
            buffer = sec
        if buffer:
            chunks.append({"text": buffer, "source": source, "chunk_index": len(chunks)})
        return chunks

    def _chunk(self, text: str, source: str, pages: list[tuple[int, str]] | None = None) -> list[dict]:
        if pages:
            paragraphs = []
            for page_num, page_text in pages:
                for para in page_text.split("\n\n"):
                    stripped = para.strip()
                    if stripped:
                        paragraphs.append({"text": stripped, "page": page_num})
        else:
            paragraphs = [{"text": p.strip(), "page": 1} for p in text.split("\n\n") if p.strip()]
        chunks = []
        current, cur_len, cur_pages = [], 0, set()
        for para in paragraphs:
            if cur_len + len(para["text"]) > self.chunk_size and current:
                chunks.append({"text": "\n\n".join(current), "source": source, "chunk_index": len(chunks)})
                ov = "\n\n".join(current)[-self.chunk_overlap:] if self.chunk_overlap else ""
                current = [ov] if ov.strip() else []
                cur_len = len(ov) if ov.strip() else 0
                cur_pages = set(cur_pages)
            current.append(para["text"])
            cur_len += len(para["text"])
            cur_pages.add(para["page"])
        if current:
            chunks.append({"text": "\n\n".join(current), "source": source, "chunk_index": len(chunks)})
        return chunks
