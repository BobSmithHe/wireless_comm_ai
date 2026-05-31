# API Documentation

Base URL: `http://localhost:8000`

## Auth

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/api/auth/register` | `{username, email, password}` | `{id, username, email}` |
| POST | `/api/auth/login` | `{username, password}` | `{access_token, refresh_token}` |
| POST | `/api/auth/refresh` | `{refresh_token}` | `{access_token}` |
| GET | `/api/auth/me` | - | `{id, username, email}` |

## Chat

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/api/chat` | `{message, conversation_id?}` | SSE stream |

## Code

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/api/code/execute` | `{code, language, stdin?}` | `{stdout, stderr, exit_code}` |

## Memory

| Method | Path | Params | Response |
|--------|------|--------|----------|
| GET | `/api/memory` | `?query&limit&layer` | `[{content, score, layer}]` |
| DELETE | `/api/memory/{id}` | - | `{status}` |

## Knowledge

| Method | Path | Params | Response |
|--------|------|--------|----------|
| GET | `/api/knowledge/search` | `?query&top_k` | `[{content, score, source}]` |
| POST | `/api/knowledge/upload` | file | `{id, filename, chunks}` |
