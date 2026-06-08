"""Application configuration — settings, database, security."""
from functools import lru_cache
from datetime import datetime, timedelta, timezone
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from jose import jwt, JWTError
import bcrypt

Base = declarative_base()
engine = None
SessionLocal = None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


class Settings(BaseSettings):
    app_name: str = "WirelessCommAI"
    app_version: str = "0.1.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8765

    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "wireless_comm_ai"

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    milvus_uri: str = "http://localhost:19530"
    milvus_token: str = ""
    milvus_db_name: str = "milvus_database"

    embedding_model: str = "BAAI/bge-large-zh-v1.5"
    embedding_dimension: int = 1024
    embedding_device: str = "cpu"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    tavily_api_key: str = ""

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"
    langfuse_enabled: bool = True

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440
    jwt_refresh_token_expire_days: int = 7

    code_exec_timeout: int = 30
    code_exec_max_memory: str = "256m"
    sandbox_mode: str = "subprocess"

    kb_data_dir: str = "./data/textbook"
    kb_chunk_size: int = 1000
    kb_chunk_overlap: int = 200
    kb_max_upload_size_mb: int = 50
    kb_context_budget_tokens: int = 2000
    kb_hybrid_search: bool = True
    kb_rerank_enabled: bool = True
    zhipu_api_key: str = ""
    zhipu_rerank_url: str = "https://open.bigmodel.cn/api/paas/v4/rerank"
    zhipu_rerank_model: str = "rerank"

    context_compression_enabled: bool = True
    context_compression_trigger_rounds: int = 10
    context_compression_keep_rounds: int = 5
    context_compression_summary_max_tokens: int = 500

    @property
    def database_url(self) -> str:
        return f"mysql+pymysql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def database_url_async(self) -> str:
        return f"mysql+aiomysql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    s = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=s.jwt_access_token_expire_minutes)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, s.jwt_secret_key, algorithm=s.jwt_algorithm)


def create_refresh_token(data: dict) -> str:
    s = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=s.jwt_refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, s.jwt_secret_key, algorithm=s.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().jwt_secret_key, algorithms=[get_settings().jwt_algorithm])
    except JWTError:
        return None


# Lazy-init database engine after Settings class is defined
def _init_engine():
    global engine, SessionLocal
    if engine is None:
        s = Settings()
        engine = create_engine(s.database_url, echo=False, pool_pre_ping=True)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_init_engine()
