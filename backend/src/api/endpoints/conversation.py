"""Conversation CRUD endpoints with Redis caching for fast switching."""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...database.models import Conversation, Message
from ...cache.redis_client import get_redis
from ..dependencies import get_current_user

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class ToolResultRequest(BaseModel):
    code: str
    language: str = "python"
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    attempt: int = 1


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("")
def create_conversation(user=Depends(get_current_user), db: Session = Depends(get_db)):
    conv = Conversation(user_id=user.id, title="新对话")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return {"id": conv.id, "title": conv.title, "created_at": str(conv.created_at)}


@router.get("")
def list_conversations(user=Depends(get_current_user), db: Session = Depends(get_db)):
    convs = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    return [
        {
            "id": c.id, "title": c.title,
            "message_count": db.query(Message).filter(
                Message.user_id == user.id, Message.conversation_id == c.id
            ).count(),
            "created_at": str(c.created_at), "updated_at": str(c.updated_at),
        }
        for c in convs
    ]


@router.get("/{conv_id}")
async def get_conversation(
    conv_id: int,
    before: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conv_id, Conversation.user_id == user.id)
        .first()
    )
    if not conv:
        raise HTTPException(404, "Conversation not found")

    # Pagination requests skip cache
    if before:
        q = db.query(Message).filter(
            Message.user_id == user.id, Message.conversation_id == conv_id,
            Message.id < before,
        )
        msgs = q.order_by(Message.id.desc()).limit(limit).all()
        msgs.reverse()
        total = db.query(Message).filter(
            Message.user_id == user.id, Message.conversation_id == conv_id
        ).count()
        return {
            "conversation_id": conv.id, "id": conv.id, "title": conv.title,
            "messages": [{"id": m.id, "role": m.role, "content": m.content} for m in msgs],
            "has_more": len(msgs) == limit, "total": total,
        }

    # Try Redis cache (written on last chat message) — fresh by design
    try:
        r = await get_redis()
        cached = await r.get(f"conv_msgs:{user.id}:{conv_id}")
        if cached:
            msgs = json.loads(cached)
            total = db.query(Message).filter(
                Message.user_id == user.id, Message.conversation_id == conv_id
            ).count()
            return {
                "conversation_id": conv.id, "id": conv.id, "title": conv.title,
                "messages": msgs,
                "has_more": len(msgs) == limit and total > limit,
                "total": total,
            }
    except Exception:
        pass

    # Cache miss — query MySQL
    msgs = (
        db.query(Message)
        .filter(Message.user_id == user.id, Message.conversation_id == conv_id)
        .order_by(Message.id.desc()).limit(limit).all()
    )
    msgs.reverse()
    total = db.query(Message).filter(
        Message.user_id == user.id, Message.conversation_id == conv_id
    ).count()

    return {
        "conversation_id": conv.id, "id": conv.id, "title": conv.title,
        "messages": [{"id": m.id, "role": m.role, "content": m.content} for m in msgs],
        "has_more": len(msgs) == limit, "total": total,
    }


@router.post("/{conv_id}/tool")
async def record_tool_result(
    conv_id: int,
    req: ToolResultRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conv_id, Conversation.user_id == user.id)
        .first()
    )
    if not conv:
        raise HTTPException(404, "Conversation not found")

    user_msg = f"[工具调用 第{req.attempt}次]\n```{req.language}\n{req.code}\n```"
    assistant_msg = f"[执行结果] 退出码={req.exit_code}"
    if req.stdout:
        assistant_msg += f"\n```\n{req.stdout}\n```"
    if req.stderr:
        assistant_msg += f"\n错误:\n```\n{req.stderr}\n```"

    db.add(Message(user_id=user.id, conversation_id=conv_id, role="tool", content=user_msg))
    db.add(Message(user_id=user.id, conversation_id=conv_id, role="tool_result", content=assistant_msg))
    db.commit()

    return {"status": "recorded", "conversation_id": conv_id}


@router.delete("/{conv_id}")
async def delete_conversation(conv_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conv_id, Conversation.user_id == user.id)
        .first()
    )
    if not conv:
        raise HTTPException(404, "Conversation not found")
    db.query(Message).filter(
        Message.user_id == user.id, Message.conversation_id == conv_id
    ).delete()
    db.delete(conv)
    db.commit()

    # Clear Redis cache
    try:
        r = await get_redis()
        await r.delete(f"conv_msgs:{user.id}:{conv_id}")
    except Exception:
        pass

    return {"status": "deleted"}
