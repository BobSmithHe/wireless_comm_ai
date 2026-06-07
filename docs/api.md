# API Reference

Base: `http://localhost:8760`

Auth header: `Authorization: Bearer <access_token>`

---

## Auth

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/api/auth/register` | `{username, email, password}` | `{id, username, email, is_active}` |
| POST | `/api/auth/login` | `{username, password}` | `{access_token, refresh_token, token_type}` |
| GET | `/api/auth/me` | - | `{id, username, email}` |

---

## Chat (SSE Stream)

```
POST /api/chat/stream
Content-Type: application/json
```

```json
{
  "message": "OFDM子载波间隔是多少？",
  "conversation_id": 1,
  "use_rag": true,
  "use_web": false
}
```

Response: `text/event-stream`

```
data: {"event":"status","content":"连接成功，正在分析问题..."}

data: {"event":"status","content":"📚 正在检索知识库: OFDM子载波间隔 3GPP 定义 计算"}

data: {"event":"result","content":"找到 3 条: 4_无线信道的信道容量.md (相关度 100%) | ..."}

data: {"event":"status","content":"正在生成回答..."}

data: {"event":"answer","content":"OFDM子载波间隔定义..."}

data: {"event":"done"}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `message` | string | required | 用户消息 |
| `conversation_id` | int | null | 对话 ID，为空则新建 |
| `use_rag` | bool | true | 启用知识库检索 |
| `use_web` | bool | false | 启用 Tavily 联网搜索 |

> 记忆检索始终开启，不受 `use_rag` 控制。

---

## Conversations

| Method | Path | Params | Response |
|--------|------|--------|----------|
| POST | `/api/conversations` | - | `{id, title, created_at}` |
| GET | `/api/conversations` | - | `[{id, title, message_count}]` |
| GET | `/api/conversations/{id}` | `?limit=50&before={msg_id}` | `{id, title, messages[], has_more}` |
| DELETE | `/api/conversations/{id}` | - | `{status: "deleted"}` |

Messages cached in Redis (30min TTL), pagination via `before` cursor.

---

## Knowledge Base

### Search

```
GET /api/knowledge/search?query=OFDM&top_k=5
```

Response:
```json
{
  "results": [
    {"content": "OFDM（正交频分复用）...", "score": 0.92, "source": "4_无线信道的信道容量.md"}
  ]
}
```

### Upload

```
POST /api/knowledge/upload
Content-Type: multipart/form-data
file: <pdf|md|txt|py>
```

Response: `{filename, chunks, status: "indexed"}`

---

## Code Execution

### Execute

```
POST /api/code/execute
```

```json
{
  "code": "import numpy as np\nprint(np.pi)",
  "language": "python"
}
```

Response:
```json
{
  "success": true,
  "stdout": "3.141592653589793",
  "stderr": "",
  "exit_code": 0,
  "images": ["iVBORw0KGgo..."]
}
```

`images[]` 为 base64 PNG，由 matplotlib 生成的图表。

### Generate + Execute + Debug

```
POST /api/code/generate
```

```json
{
  "description": "生成OFDM的IFFT实现",
  "language": "python"
}
```

自动纠错重试最多 3 次，返回最终代码与执行结果。

---

## Papers (PDF)

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/api/papers/upload` | multipart `file` (.pdf) | `{paper_id, filename, summary, page_count}` |
| GET | `/api/papers` | - | `{papers: [{id, filename, summary}]}` |
| GET | `/api/papers/{id}` | - | `{id, filename, full_text, summary, messages[]}` |
| POST | `/api/papers/{id}/chat` | `{message}` | `{response, paper_id}` |
| DELETE | `/api/papers/{id}` | - | `{status}` |

---

## Health

```
GET /health → {"status": "ok", "app": "WirelessCommAI", "version": "0.1.0"}
```

---

## Rate Limiting

无。生产部署需添加。
