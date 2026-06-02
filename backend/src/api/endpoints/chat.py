import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ...config.database import get_db
from ...database.models import Conversation, Message
from ...services.chat_service import ChatService
from ...core.observability import trace_attributes
from ...cache.redis_client import get_redis
from ..dependencies import get_current_user, get_chat_service

router = APIRouter(prefix="/api", tags=["chat"])

CACHE_TTL = 1800


async def _update_redis_cache(conv_id: int, user_id: int, db: Session):
    """Write the latest 50 messages for a conversation into Redis (cache-on-write)."""
    try:
        msgs = (
            db.query(Message)
            .filter(Message.conversation_id == conv_id)
            .order_by(Message.id.desc())
            .limit(50)
            .all()
        )
        msgs.reverse()
        data = [{"id": m.id, "role": m.role, "content": m.content} for m in msgs]
        r = await get_redis()
        await r.setex(f"conv_msgs:{user_id}:{conv_id}", CACHE_TTL, json.dumps(data, ensure_ascii=False))
    except Exception:
        pass


class ChatRequest(BaseModel):
    message: str
    conversation_id: int | None = None
    system_context: str | None = None  # optional system hint (e.g., tool error for auto-fix)


class ChatResponse(BaseModel):
    response: str
    conversation_id: int
    sources: list[dict] = []


def _get_history(db: Session, conv_id: int) -> list[dict]:
    """Get conversation history for LLM context (filters out tool messages)."""
    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conv_id)
        .order_by(Message.id)
        .all()
    )
    return [
        {"role": m.role, "content": m.content}
        for m in msgs
        if m.role in ("user", "assistant", "system")  # skip tool/tool_result for LLM
    ]


def _save_msg(db: Session, user_id: int, conv_id: int, role: str, content: str) -> None:
    db.add(Message(user_id=user_id, conversation_id=conv_id, role=role, content=content))


def _get_or_create_conv(db: Session, user_id: int, conv_id: int | None) -> Conversation:
    if conv_id:
        conv = (
            db.query(Conversation)
            .filter(Conversation.id == conv_id, Conversation.user_id == user_id)
            .first()
        )
        if conv:
            return conv
    conv = Conversation(user_id=user_id, title="新对话")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
    chat_service: ChatService = Depends(get_chat_service),
):
    conv = _get_or_create_conv(db, user.id, req.conversation_id)
    history = _get_history(db, conv.id)

    # Save user message first for correct ordering: user → tools → assistant
    _save_msg(db, user.id, conv.id, "user", req.message)

    with trace_attributes(user_id=str(user.id), session_id=str(conv.id)):
        result = await chat_service.chat(
            user_id=user.id,
            message=req.message,
            conversation_id=conv.id,
            history=history,
            db_session=db,
            system_context=req.system_context,
        )

    _save_msg(db, user.id, conv.id, "assistant", result["response"])
    if conv.title == "新对话":
        conv.title = req.message[:30] + ("..." if len(req.message) > 30 else "")
    db.commit()

    # Write latest messages to Redis cache so switching back is instant
    await _update_redis_cache(conv.id, user.id, db)

    return ChatResponse(
        response=result["response"],
        conversation_id=conv.id,
        sources=result.get("sources", []),
    )


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
    chat_service: ChatService = Depends(get_chat_service),
):
    conv = _get_or_create_conv(db, user.id, req.conversation_id)
    history = _get_history(db, conv.id)
    _save_msg(db, user.id, conv.id, "user", req.message)

    async def event_stream():
        with trace_attributes(user_id=str(user.id), session_id=str(conv.id)):
            full_response = ""
            async for chunk in chat_service.chat_stream(
                user_id=user.id,
                message=req.message,
                conversation_id=conv.id,
                history=history,
                db_session=db,
            ):
                full_response += chunk
                yield f"data: {chunk}\n\n"

            _save_msg(db, user.id, conv.id, "assistant", full_response)
            if conv.title == "新对话":
                conv.title = req.message[:30] + ("..." if len(req.message) > 30 else "")
            db.commit()
            await _update_redis_cache(conv.id, user.id, db)
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
