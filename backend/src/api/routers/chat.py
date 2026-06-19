import json
import asyncio

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ...core.config import SessionLocal, get_db, get_settings
from ...database.models import Conversation, Message
from ...services.chat_service import ChatService
from ...core.observability import trace_attributes
from ...cache.redis_client import get_redis
from ...utils.logger import logger
from ..deps import get_current_user, get_chat_service

router = APIRouter(prefix="/api", tags=["chat"])

CACHE_TTL = 1800
MEMORY_MARKERS = ("记住", "请记住", "以后", "偏好", "希望")


async def _update_redis_cache(conv_id: int, user_id: int, db: Session):
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
    use_rag: bool = True
    use_web: bool = False
    system_context: str | None = None


def _get_history(db: Session, conv_id: int) -> list[dict]:
    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conv_id)
        .order_by(Message.id)
        .all()
    )
    return [
        {"role": m.role, "content": m.content}
        for m in msgs
        if m.role in ("user", "assistant", "system")
    ]


def _save_msg(db: Session, user_id: int, conv_id: int, role: str, content: str) -> Message:
    msg = Message(user_id=user_id, conversation_id=conv_id, role=role, content=content)
    db.add(msg)
    return msg


def _count_assistant_rounds(db: Session, user_id: int, conv_id: int) -> int:
    return (
        db.query(Message)
        .filter(
            Message.user_id == user_id,
            Message.conversation_id == conv_id,
            Message.role == "assistant",
        )
        .count()
    )


def _should_schedule_memory(user_message: str, assistant_rounds: int) -> bool:
    if any(marker in user_message for marker in MEMORY_MARKERS):
        return True
    interval = max(0, get_settings().memory_graph_extract_interval_rounds)
    return interval > 0 and assistant_rounds > 0 and assistant_rounds % interval == 0


async def _remember_exchange_background(
    chat_service: ChatService,
    user_id: int,
    user_message: str,
    assistant_message: str,
    source_message_id: int,
) -> None:
    db = SessionLocal()
    try:
        stored = await chat_service.remember_exchange(
            db,
            user_id=user_id,
            user_message=user_message,
            assistant_message=assistant_message,
            source_message_id=source_message_id,
        )
        logger.info(
            f"Background memory graph extraction stored {stored} edges "
            f"for user={user_id} message={source_message_id}"
        )
    except Exception as exc:
        logger.warning(f"Background memory graph extraction failed: {exc}")
    finally:
        db.close()


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
    db.commit()

    user_id = user.id
    conv_id = conv.id
    is_new = conv.title == "新对话"
    if is_new:
        conv.title = req.message[:30] + ("..." if len(req.message) > 30 else "")
        db.commit()

    async def event_stream():
        yield 'data: {"event":"status","content":"连接成功，正在分析问题..."}\n\n'
        with trace_attributes(user_id=str(user_id), session_id=str(conv_id)):
            full_response = ""
            async for line in chat_service.chat_sse(
                user_id=user_id,
                message=req.message,
                conversation_id=conv_id,
                history=history,
                db_session=db,
                use_rag=req.use_rag,
                use_web=req.use_web,
                system_context=req.system_context,
            ):
                yield line
                if '"event":"answer"' in line:
                    import json as _json
                    try:
                        data = _json.loads(line[6:].strip())
                        full_response += data.get("content", "")
                    except Exception:
                        pass

            if full_response:
                assistant_msg = _save_msg(db, user_id, conv_id, "assistant", full_response)
                db.commit()
                db.refresh(assistant_msg)
                assistant_rounds = _count_assistant_rounds(db, user_id, conv_id)
                if _should_schedule_memory(req.message, assistant_rounds):
                    asyncio.create_task(_remember_exchange_background(
                        chat_service=chat_service,
                        user_id=user_id,
                        user_message=req.message,
                        assistant_message=full_response,
                        source_message_id=assistant_msg.id,
                    ))
            else:
                db.commit()
            await _update_redis_cache(conv_id, user_id, db)
            yield 'data: {"event":"done"}\n\n'

    return StreamingResponse(event_stream(), media_type="text/event-stream")
