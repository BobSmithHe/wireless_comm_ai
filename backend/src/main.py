from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config.settings import get_settings
from .utils.logger import logger
from .api.endpoints import auth, chat, code, knowledge, conversation, papers

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")

    # Init Langfuse observability
    from .core.observability import init_langfuse, flush, shutdown
    init_langfuse()

    # Auto-create database tables
    from .config.database import engine, Base
    from .database.models import User, Conversation, Knowledge, Paper, PaperMessage, Project  # noqa: F811
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified")

    yield

    logger.info(f"Shutting down {settings.app_name}")
    flush()


def _preload_knowledge_base(kb) -> None:
    """Import knowledge base documents on startup."""
    import os
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge_base")
    if not os.path.isdir(data_dir):
        logger.warning(f"Knowledge base directory not found: {data_dir}")
        return

    count = 0
    for root, dirs, files in os.walk(data_dir):
        for fname in files:
            if fname.endswith((".md", ".txt")):
                filepath = os.path.join(root, fname)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                ids = kb.add_documents(
                    texts=[content],
                    metadatas=[{"source": fname, "category": os.path.basename(root)}],
                )
                count += len(ids)
    logger.info(f"Knowledge base loaded: {count} chunks from {data_dir}")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5178",
        "http://localhost:5179",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5178",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(code.router)
app.include_router(knowledge.router)
app.include_router(conversation.router)
app.include_router(papers.router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}
