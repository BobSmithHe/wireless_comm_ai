import os
import tempfile
import uuid

from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException

from ...core.rag.knowledge_base import KnowledgeBase
from ...core.rag.document_loader import DocumentLoader
from ...core.config import get_settings
from ..deps import get_current_user, get_kb

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

_settings = get_settings()
ALLOWED_EXTENSIONS = {".md", ".txt", ".py", ".pdf"}


def _make_loader() -> DocumentLoader:
    return DocumentLoader(
        chunk_size=_settings.kb_chunk_size,
        chunk_overlap=_settings.kb_chunk_overlap,
    )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@router.get("/search")
async def search_knowledge(
    query: str = Query(..., description="Search query"),
    top_k: int = Query(default=5, ge=1, le=20),
    user=Depends(get_current_user),
    kb: KnowledgeBase = Depends(get_kb),
):
    results = await kb.search(query, top_k)
    return {
        "results": [
            {"content": r.content, "score": r.score, "source": r.source}
            for r in results
        ]
    }


# ---------------------------------------------------------------------------
# Upload (supports .md, .txt, .py, .pdf)
# ---------------------------------------------------------------------------


@router.post("/upload")
async def upload_knowledge(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    kb: KnowledgeBase = Depends(get_kb),
):
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Check file size
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > _settings.kb_max_upload_size_mb:
        raise HTTPException(
            400,
            f"File too large ({size_mb:.1f} MB). Max: {_settings.kb_max_upload_size_mb} MB",
        )

    # Write to temp file so the loader can read it
    suffix = ext if ext != ".py" else ".py"
    tmp_path = os.path.join(tempfile.gettempdir(), f"kb_upload_{uuid.uuid4().hex}{suffix}")
    try:
        with open(tmp_path, "wb") as f:
            f.write(content)

        loader = _make_loader()
        chunks = loader.load(tmp_path, file.filename)

        if not chunks:
            raise HTTPException(400, "No extractable text found in the file")

        for c in chunks:
            kb.add_document(
                text=c["text"],
                metadata={
                    "source": c["source"],
                    "page": c.get("page", []),
                    "chunk_index": c["chunk_index"],
                },
            )

        return {
            "filename": file.filename,
            "chunks": len(chunks),
            "status": "indexed",
        }
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Paper / document management
# ---------------------------------------------------------------------------


@router.get("/papers")
async def list_papers(
    user=Depends(get_current_user),
    kb: KnowledgeBase = Depends(get_kb),
):
    """List all uploaded documents (papers) with chunk counts."""
    docs = kb.list_documents()
    return {"papers": docs, "count": len(docs)}


@router.delete("/papers/{paper_id}")
async def delete_paper(
    paper_id: str,
    user=Depends(get_current_user),
    kb: KnowledgeBase = Depends(get_kb),
):
    """Delete a paper and all its chunks from the knowledge base."""
    removed = kb.remove_document(paper_id)
    if removed == 0:
        raise HTTPException(404, f"Paper '{paper_id}' not found")
    return {"status": "deleted", "paper_id": paper_id, "chunks_removed": removed}
