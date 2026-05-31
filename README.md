# Wireless Communications AI Agent

An AI Agent system for wireless communications research and engineering.

**Core features**: Agent loop with task planning + tool execution, four-stage hybrid RAG, context compression with vector-indexed memory, Docker sandbox, Langfuse observability, and PDF paper reading.

---

## Architecture

```
                         ┌──────────────────────┐
                         │   Vue 3 Frontend     │
                         │   localhost:5173     │
                         └──────────┬───────────┘
                                    │ REST / SSE
                         ┌──────────┴───────────┐
                         │   FastAPI Backend    │
                         │                      │
          ┌──────────────┼──────────────────────┼──────────────┐
          │              │                      │              │
          ▼              ▼                      ▼              ▼
   ChatService      AgentCore           CodeExecutor    KnowledgeBase
   (orchestrator)   (plan + tools)      (sandbox)       (hybrid RAG)
          │              │                      │              │
          └──────────────┼──────────────────────┼──────────────┘
                         │                      │
          ┌──────────────┼──────────────┬───────┴──────────┐
          ▼              ▼              ▼                  ▼
       MySQL        ChromaDB         Redis           Docker Sandbox
    (users/msgs)   (vectors)        (cache)         (code exec)
```

### Agent Loop

```
User Query
  │
  ├─ Compress history (if over budget)
  │    └─ Old messages → LLM summary + vector index
  │
  ├─ Retrieve compressed history (passive injection)
  │    └─ ChromaDB semantic search, filtered by conversation
  │
  ├─ [Agent mode only]
  │    └─ LLMTaskPlanner → JSON task plan
  │         ├─ _tool_search_knowledge → hybrid RAG pipeline
  │         ├─ _tool_generate_code    → DeepSeek LLM
  │         └─ _tool_execute_code     → Docker sandbox
  │
  └─ Synthesize final response
```

### RAG Pipeline

```
Query
  ├─ BM25 keyword search (TfidfVectorizer)
  ├─ Vector semantic search (sentence-transformers, ChromaDB HNSW)
  ├─ RRF fusion (reciprocal rank, k=60)
  ├─ LLM Reranker (DeepSeek pointwise scoring 1-5)
  └─ Context Packer (greedy token-budget bin packing)
       └─ Top-k chunks
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- MySQL 8.0
- Redis 7
- Docker (optional, for sandbox)

### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # edit with your credentials
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run serve                 # → http://localhost:5173
```

### Docker Sandbox (optional)

```bash
docker build -t wcai-sandbox ./sandbox
# Set SANDBOX_MODE=docker in backend/.env
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
| POST | `/api/chat` | `{message, conversation_id?, use_agent?}` | Send message |
| POST | `/api/chat/stream` | `{message, conversation_id?}` | Streaming response |

### Conversations

| Method | Path | Params | Description |
|--------|------|--------|-------------|
| POST | `/api/conversations` | - | Create |
| GET | `/api/conversations` | - | List |
| GET | `/api/conversations/{id}` | `?limit=50&before={msg_id}` | Messages |
| DELETE | `/api/conversations/{id}` | - | Delete |

### Knowledge Base

| Method | Path | Params/Body | Description |
|--------|------|-------------|-------------|
| GET | `/api/knowledge/search` | `?query=...&top_k=5` | Hybrid search |
| POST | `/api/knowledge/upload` | FormData `file` (pdf/md/txt/py) | Upload document |
| GET | `/api/knowledge/papers` | - | List documents |
| DELETE | `/api/knowledge/papers/{id}` | - | Delete document |

### Papers

| Method | Path | Body | Description |
|--------|------|------|-------------|
| POST | `/api/papers/upload` | FormData `file` (pdf) | Upload + auto-summarize |
| GET | `/api/papers` | - | List papers |
| GET | `/api/papers/{id}` | - | Detail + history |
| POST | `/api/papers/{id}/chat` | `{message}` | Chat with paper |
| DELETE | `/api/papers/{id}` | - | Delete |

### Code Execution

| Method | Path | Body | Description |
|--------|------|------|-------------|
| POST | `/api/code/execute` | `{code, language}` | Execute code |

---

## Configuration

All settings via `backend/.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | - | DeepSeek API key |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | Model for chat + planning |
| `SANDBOX_MODE` | `subprocess` | `docker` for production |
| `CONTEXT_COMPRESSION_ENABLED` | `true` | Enable compression |
| `CONTEXT_COMPRESSION_BUDGET_TOKENS` | `4000` | History token budget |
| `KB_HYBRID_SEARCH` | `true` | BM25 + vector hybrid |
| `KB_RERANK_ENABLED` | `true` | LLM reranker |
| `KB_CONTEXT_BUDGET_TOKENS` | `2000` | Context packer budget |
| `LANGFUSE_ENABLED` | `false` | Langfuse tracing |

---

## Testing

```bash
cd backend

# All tests
pytest tests/ -v

# Specific modules
pytest tests/test_context_compressor.py -v
pytest tests/test_chat_service.py -v

# RAG evaluation
python -c "
from src.eval.evaluator import RAGEvaluator
# See eval/test_cases.py for ground-truth data
"
```

---

## Project Structure

```
backend/
├── src/
│   ├── api/endpoints/       # FastAPI routes
│   ├── core/
│   │   ├── agent/           # Agent loop, planner, tools
│   │   ├── context/         # Compressor, ConversationMemory
│   │   ├── rag/             # KnowledgeBase, hybrid retrieval
│   │   ├── code/            # Docker sandbox executor
│   │   ├── llm/             # DeepSeek client
│   │   └── observability/   # Langfuse integration
│   ├── services/            # ChatService (main orchestrator)
│   ├── config/              # Pydantic settings
│   ├── database/            # SQLAlchemy models
│   ├── cache/               # Redis client
│   └── eval/                # RAG evaluation framework
├── sandbox/                 # Docker sandbox Dockerfile
├── data/knowledge_base/     # Preloaded domain documents
├── data/chroma/             # ChromaDB persistent storage
└── tests/                   # pytest tests
frontend/
├── src/
│   ├── views/               # Page components
│   ├── components/          # Shared components
│   ├── router/              # Vue Router
│   └── api/                 # Axios client
└── package.json
```
