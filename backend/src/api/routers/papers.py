"""
Paper reading API — upload PDFs, auto-summarise, persist to MySQL.
"""
import os
import tempfile
import uuid
import time

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.rag.document_loader import DocumentLoader
from ...core.llm.client import DeepSeekClient
from ...core.config import get_db
from ...database.models import Paper, PaperMessage
from ..deps import get_current_user, get_llm

router = APIRouter(prefix="/api/papers", tags=["papers"])

_loader = DocumentLoader()

MAX_SUMMARY_TEXT = 30000
MAX_CONTEXT_TEXT = 30000
MAX_HISTORY_TURNS = 20


class PaperChatRequest(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post("/upload")
async def upload_paper(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    llm: DeepSeekClient = Depends(get_llm),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext != ".pdf":
        raise HTTPException(400, f"Only PDF files are supported, got '{ext}'")

    content = await file.read()
    mb = len(content) / (1024 * 1024)
    if mb > 50:
        raise HTTPException(400, f"File too large ({mb:.1f} MB). Max: 50 MB")

    tmp_path = os.path.join(tempfile.gettempdir(), f"paper_{uuid.uuid4().hex}.pdf")
    try:
        with open(tmp_path, "wb") as f:
            f.write(content)

        chunks = _loader.load(tmp_path, file.filename)
        if not chunks:
            raise HTTPException(400, "No extractable text found in the PDF")

        full_text = "\n\n".join(c["text"] for c in chunks)
        pages = set()
        for c in chunks:
            pages.update(c.get("page", []))

        summary_text = full_text[:MAX_SUMMARY_TEXT]
        if len(full_text) > MAX_SUMMARY_TEXT:
            summary_text += "\n\n" + full_text[-5000:]

        summary = await _generate_summary(llm, file.filename, summary_text)

        paper = Paper(
            id=uuid.uuid4().hex[:12],
            user_id=user.id,
            filename=file.filename,
            full_text=full_text,
            summary=summary,
            page_count=len(pages),
            char_count=len(full_text),
        )
        db.add(paper)
        db.commit()
        db.refresh(paper)

        return {
            "paper_id": paper.id,
            "filename": paper.filename,
            "summary": paper.summary,
            "page_count": paper.page_count,
            "char_count": paper.char_count,
        }
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get("")
async def list_papers(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    papers = (
        db.query(Paper)
        .filter(Paper.user_id == user.id)
        .order_by(Paper.created_at.desc())
        .all()
    )
    return {
        "papers": [
            {
                "id": p.id,
                "filename": p.filename,
                "summary": p.summary,
                "page_count": p.page_count,
                "char_count": p.char_count,
            }
            for p in papers
        ]
    }


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


@router.get("/{paper_id}")
async def get_paper(
    paper_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = db.query(Paper).filter(Paper.id == paper_id, Paper.user_id == user.id).first()
    if not p:
        raise HTTPException(404, "Paper not found")
    return {
        "id": p.id,
        "filename": p.filename,
        "full_text": p.full_text,
        "summary": p.summary,
        "page_count": p.page_count,
        "char_count": p.char_count,
        "messages": [
            {"role": m.role, "content": m.content}
            for m in p.messages
        ],
    }


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


@router.post("/{paper_id}/chat")
async def chat_with_paper(
    paper_id: str,
    req: PaperChatRequest,
    user=Depends(get_current_user),
    llm: DeepSeekClient = Depends(get_llm),
    db: Session = Depends(get_db),
):
    p = db.query(Paper).filter(Paper.id == paper_id, Paper.user_id == user.id).first()
    if not p:
        raise HTTPException(404, "Paper not found")

    message = req.message.strip()
    if not message:
        raise HTTPException(400, "Message is empty")

    # Build paper context
    full_text = p.full_text
    if len(full_text) <= MAX_CONTEXT_TEXT:
        paper_context = full_text
    else:
        head_size = int(MAX_CONTEXT_TEXT * 0.65)
        tail_size = int(MAX_CONTEXT_TEXT * 0.35)
        paper_context = full_text[:head_size] + "\n\n...\n\n" + full_text[-tail_size:]

    system_prompt = (
        f'You are reading the academic paper "{p.filename}". '
        f"Answer the user's questions based SOLELY on the paper content below. "
        f"If the answer is not in the paper, say so — do not make things up.\n\n"
        f"=== PAPER CONTENT ===\n{paper_context}"
    )

    # Build messages: system + recent history + current question
    recent = p.messages[-MAX_HISTORY_TURNS * 2:]

    llm_messages = [{"role": "system", "content": system_prompt}]
    for m in recent:
        llm_messages.append({"role": m.role, "content": m.content})
    llm_messages.append({"role": "user", "content": message})

    response = await llm.raw_chat(llm_messages, temperature=0.3, max_tokens=4096)

    # Persist Q&A
    db.add(PaperMessage(paper_id=paper_id, role="user", content=message))
    db.add(PaperMessage(paper_id=paper_id, role="assistant", content=response))
    db.commit()

    return {"response": response, "paper_id": paper_id}


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.delete("/{paper_id}")
async def delete_paper(
    paper_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = db.query(Paper).filter(Paper.id == paper_id, Paper.user_id == user.id).first()
    if not p:
        raise HTTPException(404, "Paper not found")
    db.delete(p)
    db.commit()
    return {"status": "deleted", "paper_id": paper_id}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _generate_summary(llm: DeepSeekClient, filename: str, text: str) -> str:
    prompt = (
        "You are reading an academic paper. Summarise it concisely in 3-5 sentences, covering:\n"
        "- What is the main topic / research question?\n"
        "- What methodology or approach is used?\n"
        "- What are the key findings or contributions?\n\n"
        f"Paper filename: {filename}\n\n"
        f"=== PAPER TEXT ===\n{text}\n\n"
        "Summary:"
    )
    try:
        summary = await llm.raw_chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )
        return summary.strip()
    except Exception:
        return f"[Could not auto-summarise] {filename}"
