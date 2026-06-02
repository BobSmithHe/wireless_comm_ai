# Wireless Communications AI Agent

AI Agent system for wireless communications research and engineering.

**Core features**: LLM-driven tool calling (RAG + memory retrieval), Milvus vector database, round-based context compression with vector-indexed memory, Docker sandbox for code execution, PDF paper reading with chat.

---

## Architecture

```
                         ┌──────────────────────┐
                         │   Vue 3 Frontend     │
                         │   localhost:5178     │
                         └──────────┬───────────┘
                                    │ REST / SSE
                         ┌──────────┴───────────┐
                         │   FastAPI Backend    │
                         │                      │
          ┌──────────────┼──────────────────────┼──────────────┐
          │              │                      │              │
          ▼              ▼                      ▼              ▼
   ChatService      DeepSeekClient       CodeExecutor    KnowledgeBase
   (agent loop)     (LLM gateway)        (sandbox)       (hybrid RAG)
          │              │                      │              │
          └──────────────┼──────────────────────┼──────────────┘
                         │                      │
          ┌──────────────┼──────────────┬───────┴──────────┐
          ▼              ▼              ▼                  ▼
       MySQL          Milvus          Redis          Docker Sandbox
    (users/msgs)   (vectors)        (cache)         (code exec)
```

### Chat Flow (LLM Tool Calling)

```
User Message
  │
  ├─ Compress history (≥10 messages → archive first N-5)
  │    └─ Archived messages → Milvus (full text) + LLM summary
  │
  ├─ LLM decides: need tools?
  │    ├─ search_knowledge(query) → Milvus knowledge_base (hybrid BM25 + vector)
  │    ├─ search_memory(query)     → Milvus conversation_memory (vector, user-scoped)
  │    └─ No tools needed         → return response directly
  │
  └─ Tool results injected → LLM synthesizes final answer
```

### RAG Pipeline (knowledge_base collection)

```
Query
  ├─ BM25 sparse search (server-side via Milvus Function)
  ├─ Dense vector search (BAAI/bge-large-zh-v1.5, 1024-dim)
  ├─ RRF fusion (reciprocal rank, k=60)
  └─ Optional: LLM Reranker (ZhipuAI)
```

### Memory Strategy (conversation_memory collection)

```
10 messages (5 Q&A pairs)
  → Archive first 5 messages → Milvus (384-dim all-MiniLM-L6-v2)
  → Compress into LLM summary → injected as system message
  → Keep last 5 messages as-is in context
  → LLM can call search_memory to retrieve archived content
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- MySQL 8.0
- Redis 7
- Milvus 2.4+
- Docker (optional, for sandbox)

### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # edit with your credentials
python -m uvicorn src.main:app --host 0.0.0.0 --port 8765 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run serve                 # → http://localhost:5178
```

### Docker Sandbox (optional)

```bash
cd backend
docker build -t wcai-sandbox ./sandbox
# Set SANDBOX_MODE=docker in backend/.env
```

### Knowledge Base Import

```bash
cd backend
python -m src.core.rag.insert_data
```

---

## API Reference

### Auth

| Method | Path | Body | Description |
|--------|------|------|-------------|
| POST | `/api/auth/register` | `{username, email, password}` | Register |
| POST | `/api/auth/login` | `{username, password}` | Login → JWT |
| GET | `/api/auth/me` | - | Current user |

### Chat

| Method | Path | Body | Description |
|--------|------|------|-------------|
| POST | `/api/chat` | `{message, conversation_id?, system_context?}` | Send message (LLM auto-selects tools) |
| POST | `/api/chat/stream` | `{message, conversation_id?}` | Streaming response (SSE) |

### Conversations

| Method | Path | Params | Description |
|--------|------|--------|-------------|
| POST | `/api/conversations` | - | Create conversation |
| GET | `/api/conversations` | - | List conversations |
| GET | `/api/conversations/{id}` | `?limit=50&before={msg_id}` | Get messages (paginated, Redis-cached) |
| DELETE | `/api/conversations/{id}` | - | Delete conversation |

### Knowledge Base

| Method | Path | Params/Body | Description |
|--------|------|-------------|-------------|
| GET | `/api/knowledge/search` | `?query=...&top_k=5` | Hybrid search (BM25 + vector) |
| POST | `/api/knowledge/upload` | FormData `file` (pdf/md/txt/py) | Upload document |
| GET | `/api/knowledge/papers` | - | List documents |
| DELETE | `/api/knowledge/papers/{id}` | - | Delete document |

### Papers (PDF reading)

| Method | Path | Body | Description |
|--------|------|------|-------------|
| POST | `/api/papers/upload` | FormData `file` (pdf) | Upload + auto-summarize |
| GET | `/api/papers` | - | List papers |
| GET | `/api/papers/{id}` | - | Detail + chat history |
| POST | `/api/papers/{id}/chat` | `{message}` | Chat with paper |
| DELETE | `/api/papers/{id}` | - | Delete |

### Code Execution

| Method | Path | Body | Description |
|--------|------|------|-------------|
| POST | `/api/code/execute` | `{code, language?}` | Execute code (Docker/subprocess), returns images as base64 |
| POST | `/api/code/generate` | `{description, language?}` | Generate + execute + debug (3 retries) |

---

## Configuration

All settings via `backend/.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | - | DeepSeek API key (OpenAI-compatible) |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | Model for chat |
| `MILVUS_URI` | `http://localhost:19530` | Milvus connection |
| `EMBEDDING_MODEL` | `BAAI/bge-large-zh-v1.5` | Knowledge base embedding model |
| `EMBEDDING_DIMENSION` | `1024` | Embedding vector dimension |
| `SANDBOX_MODE` | `subprocess` | `docker` for production isolation |
| `CONTEXT_COMPRESSION_ENABLED` | `true` | Enable history compression |
| `CONTEXT_COMPRESSION_TRIGGER_ROUNDS` | `10` | Messages before compression triggers |
| `CONTEXT_COMPRESSION_KEEP_ROUNDS` | `5` | Recent messages to keep in context |
| `CONTEXT_COMPRESSION_SUMMARY_MAX_TOKENS` | `500` | Max tokens for LLM summary |
| `KB_HYBRID_SEARCH` | `true` | BM25 + vector hybrid search |
| `KB_RERANK_ENABLED` | `true` | ZhipuAI LLM reranker |
| `KB_CONTEXT_BUDGET_TOKENS` | `2000` | Context packer token budget |

---

## Testing

```bash
cd backend
pytest tests/ -v
```

---

## Project Structure

```
backend/
├── src/
│   ├── api/endpoints/       # FastAPI routes (auth, chat, code, knowledge, papers, conversation)
│   ├── core/
│   │   ├── context/         # ContextCompressor, ConversationMemory (Milvus-backed)
│   │   ├── rag/             # KnowledgeBase, SmartMarkdownSplitter, hybrid retrieval
│   │   ├── code/            # CodeGenerator, CodeDebugger, CodeExecutor (Docker sandbox)
│   │   ├── llm/             # DeepSeekClient (OpenAI-compatible, tool-calling support)
│   │   └── observability/   # Langfuse tracing
│   ├── services/            # ChatService (agent loop + tool orchestration)
│   ├── config/              # Pydantic settings
│   ├── database/            # SQLAlchemy models (User, Conversation, Message, Paper)
│   ├── cache/               # Redis client
│   ├── utils/               # Logger, password helpers
│   └── eval/                # RAG evaluation framework
├── sandbox/                 # Docker sandbox Dockerfile (numpy/scipy/matplotlib + CJK fonts)
├── data/knowledge_base/     # Preloaded wireless domain documents (markdown)
└── tests/                   # pytest tests
frontend/
├── src/
│   ├── views/               # Page components (Chat, CodeEditor, Knowledge, Papers, Home, Login)
│   ├── components/          # HeaderBar, Sidebar, MarkdownBlock
│   ├── router/              # Vue Router with auth guard
│   ├── store/               # Pinia auth store
│   └── api/                 # Axios client with JWT interceptor
└── package.json
```
