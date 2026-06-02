from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "WirelessCommAI"
    app_version: str = "0.1.0"
    debug: bool = False

    host: str = "0.0.0.0"
    port: int = 8000

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

    langfuse_public_key: str = "pk-lf-b80998a5-9063-4bbe-9930-896635c54b44"
    langfuse_secret_key: str = "sk-lf-8fd3ce81-01bc-487f-bec5-1857c1505c2a"
    langfuse_host: str = "http://localhost:3000"
    langfuse_enabled: bool = True

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    code_exec_timeout: int = 30
    code_exec_max_memory: str = "256m"
    sandbox_mode: str = "subprocess"

    # ---- Knowledge Base ----
    kb_data_dir: str = "./data/knowledge_base"
    kb_chunk_size: int = 1000
    kb_chunk_overlap: int = 200
    kb_max_upload_size_mb: int = 50
    kb_context_budget_tokens: int = 2000
    kb_hybrid_search: bool = True
    kb_rerank_enabled: bool = True

    # ---- Context Compression ----
    context_compression_enabled: bool = True
    context_compression_trigger_rounds: int = 10
    context_compression_keep_rounds: int = 5
    context_compression_summary_max_tokens: int = 500

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def database_url_async(self) -> str:
        return (
            f"mysql+aiomysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
