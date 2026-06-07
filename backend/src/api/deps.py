from functools import lru_cache
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from ..core.config import get_db
from ..core.config import get_settings
from ..core.llm.client import DeepSeekClient
from ..core.rag.knowledge_base import KnowledgeBase
from ..core.context.conversation_memory import ConversationMemory
from ..core.code.executor import CodeExecutor
from ..core.code.code_generator import CodeGenerator
from ..core.code.debugger import CodeDebugger
from ..services.auth_service import AuthService
from ..services.chat_service import ChatService
from ..services.code_service import CodeService
from ..cache.cache_manager import CacheManager

security = HTTPBearer()


# ---- Singletons (lazy init) ----

_settings = get_settings()

_llm: DeepSeekClient | None = None
_kb: KnowledgeBase | None = None
_memory: ConversationMemory | None = None
_code_exec: CodeExecutor | None = None
_code_gen: CodeGenerator | None = None
_code_debug: CodeDebugger | None = None
_auth_svc: AuthService | None = None
_chat_svc: ChatService | None = None
_code_svc: CodeService | None = None
_cache: CacheManager | None = None


def get_llm() -> DeepSeekClient:
    global _llm
    if _llm is None:
        _llm = DeepSeekClient()
    return _llm


def get_kb() -> KnowledgeBase:
    global _kb
    if _kb is None:
        _kb = KnowledgeBase(
            llm_client=get_llm(),
            milvus_uri=_settings.milvus_uri,
            milvus_token=_settings.milvus_token or None,
            milvus_db_name=_settings.milvus_db_name,
            embedding_model=_settings.embedding_model,
            embedding_dimension=_settings.embedding_dimension,
            embedding_device=_settings.embedding_device,
        )
    return _kb


def get_conversation_memory() -> ConversationMemory:
    global _memory
    if _memory is None:
        _memory = ConversationMemory(
            milvus_uri=_settings.milvus_uri,
            milvus_token=_settings.milvus_token or None,
            milvus_db_name=_settings.milvus_db_name,
        )
    return _memory


def get_code_executor() -> CodeExecutor:
    global _code_exec
    if _code_exec is None:
        _code_exec = CodeExecutor()
    return _code_exec


def get_code_generator() -> CodeGenerator:
    global _code_gen
    if _code_gen is None:
        _code_gen = CodeGenerator(get_llm())
    return _code_gen


def get_code_debugger() -> CodeDebugger:
    global _code_debug
    if _code_debug is None:
        _code_debug = CodeDebugger(get_llm())
    return _code_debug


def get_auth_service() -> AuthService:
    global _auth_svc
    if _auth_svc is None:
        _auth_svc = AuthService()
    return _auth_svc


def get_chat_service() -> ChatService:
    global _chat_svc
    if _chat_svc is None:
        _chat_svc = ChatService(get_llm(), get_kb(), get_code_executor(), get_conversation_memory())
    return _chat_svc


def get_code_service() -> CodeService:
    global _code_svc
    if _code_svc is None:
        _code_svc = CodeService(get_code_executor(), get_code_generator(), get_code_debugger())
    return _code_svc


def get_cache() -> CacheManager:
    global _cache
    if _cache is None:
        _cache = CacheManager()
    return _cache


# ---- Auth Dependency ----

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
):
    user = auth_service.get_current_user(db, credentials.credentials)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return user
