# WirelessComm AI

面向无线通信工程师和研究人员的 AI 助手系统。支持 RAG 知识库检索、长期记忆图谱、对话记忆、联网搜索、代码执行。

---

## 架构

```
Vue 3 Frontend (5173)  ──REST/SSE──  FastAPI Backend (8765)
                                          │
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
              ChatService             DeepSeekClient          CodeExecutor
           (agent loop + SSE)        (OpenAI-compat)        (Docker sandbox)
                    │                                             │
                    ├── KnowledgeBase ── Milvus (hybrid RAG)
                    ├── MemoryGraph ──── MySQL (user facts / preferences)
                    ├── ConvMemory ───── Milvus (384-dim)
                    ├── WebSearch ────── Tavily API
                    └── MySQL ────────── users / conversations / messages / memory graph
```

---

## 快速开始

### 前提

- Python 3.10+, Node.js 18+, MySQL 8.0, Redis 7, Milvus 2.4+, Docker（可选）

### 后端

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # 填入 API Key
python -m uvicorn src.main:app --host 0.0.0.0 --port 8765
```

### 前端

```bash
cd frontend
npm install
npm run serve                  # → http://localhost:5173
```

### 知识库导入

```bash
cd backend
python -m src.core.rag.insert_data
```

### Docker 沙箱（代码执行隔离）

```bash
cd backend
docker build -t wcai-sandbox ./sandbox
# .env 中设置 SANDBOX_MODE=docker
```

---

## 功能

### 对话

| 功能 | 说明 |
|------|------|
| 流式 SSE | 连接→检索→生成→完成，状态实时展示 |
| 工具调用 | LLM 自主决定 `search_knowledge` / `search_memory` / `search_web` |
| 前端开关 | 知识库、联网搜索独立控制，记忆始终在线 |

### RAG 知识库

- Milvus 存储，BM25 + 密集向量混合检索
- BAAI/bge-large-zh-v1.5 (1024维)
- 支持 PDF/Markdown/文本上传，自动 chunk 分片
- `auto_id` 主键，重启不冲突

### 记忆系统

- MySQL 轻量记忆图谱，按 `user_id` 持久化用户事实、偏好、项目背景和长期指令
- 显式记忆消息（如“记住/偏好/以后/希望”）立即触发后台抽取；普通对话按固定轮数后台抽取
- 记忆图谱跨会话检索，并在新对话中注入 system context
- 10 条消息触发压缩，前 N-5 条归档 Milvus，LLM 摘要注入上下文
- 后 5 条保留原文
- 对话向量记忆跨对话检索，user_id 隔离
- all-MiniLM-L6-v2 (384维)

### 联网搜索

- Tavily API，前端开关控制
- LLM 判断是否需要联网

### 代码执行

- Docker 沙箱隔离（无网络、只读文件系统、nobody 用户）
- 含 CJK 字体（WenQuanYi Micro Hei）
- 自动纠错重试 (最多3次)
- matplotlib 图表以 base64 返回

### 数学公式

KaTeX 渲染，支持四种格式：`$$` `\[` `$` `\(`

---

## API

### 对话

```
POST /api/chat/stream
Body: { message, conversation_id?, use_rag?, use_web? }
Response: SSE (text/event-stream)
Events: status → result → answer → done
```

### 认证

```
POST /api/auth/register  { username, email, password }
POST /api/auth/login     { username, password } → { access_token }
GET  /api/auth/me
```

### 对话管理

```
POST   /api/conversations            创建对话
GET    /api/conversations            列表
GET    /api/conversations/{id}       消息（支持分页 ?before={msg_id}）
DELETE /api/conversations/{id}       删除
```

### 知识库

```
GET  /api/knowledge/search?query=&top_k=      混合检索
POST /api/knowledge/upload                      上传文档 (multipart)
```

### 记忆图谱

```
GET    /api/memory-graph                 查看当前用户记忆图谱
POST   /api/memory-graph/edges           手动添加记忆边
DELETE /api/memory-graph/edges/{edge_id} 删除记忆边
DELETE /api/memory-graph/nodes/{node_id} 删除记忆节点
DELETE /api/memory-graph                 清空当前用户记忆图谱
```

### 代码

```
POST /api/code/execute   { code, language? }  → { stdout, stderr, exit_code, images[] }
POST /api/code/generate  { description }       → 生成+执行+纠错
```

### 论文

```
POST /api/papers/upload     上传 PDF
GET  /api/papers/{id}       查看 + 对话
POST /api/papers/{id}/chat  论文问答
```

---

## 配置

`.env` 关键变量：

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `DEEPSEEK_MODEL` | 模型 (deepseek-chat / deepseek-v4-flash) |
| `TAVILY_API_KEY` | Tavily 联网搜索 (可选) |
| `MILVUS_URI` | Milvus 地址 |
| `MILVUS_DB_NAME` | Milvus 数据库名，默认 `milvus_database` |
| `EMBEDDING_MODEL` | 嵌入模型 (BAAI/bge-large-zh-v1.5) |
| `SANDBOX_MODE` | docker / subprocess |
| `CONTEXT_COMPRESSION_TRIGGER_ROUNDS` | 压缩触发消息数 (默认10) |
| `MEMORY_GRAPH_EXTRACT_INTERVAL_ROUNDS` | 普通对话后台抽取记忆的轮数间隔 (默认2) |

---

## 项目结构

```
backend/src/
├── api/routers/      路由层 (auth, chat, code, knowledge, conversation, papers, memory_graph)
├── api/deps.py       依赖注入
├── core/
│   ├── config.py     配置+数据库+安全
│   ├── llm/          client.py (DeepSeekClient) + prompts.py
│   ├── code/         代码执行/生成/纠错
│   ├── context/      对话压缩+记忆存储
│   ├── rag/          Milvus 知识库+混合检索
│   └── observability/ Langfuse 追踪
├── services/         业务逻辑层 (chat, code, auth, memory_graph)
├── database/         SQLAlchemy Base + models
└── main.py           FastAPI 入口

frontend/src/
├── views/            Chat, CodeEditor, Knowledge, Papers, Home, Login, Register
├── components/       HeaderBar, Sidebar, MarkdownBlock
├── router/           Vue Router + auth guard
├── store/            Pinia
└── api/              Axios + JWT
```

---

## 测试

```bash
cd backend && pytest tests/ -v
```

## 效果展示
![](img/img_0.png)
![](img/img_1.png)
![](img/img_2.png)
![](img/img_3.png)
![](img/img_4.png)
