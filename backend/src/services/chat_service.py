import json
from typing import AsyncIterator
from ..core.llm.client import DeepSeekClient
from ..core.llm.prompts import RAG_TOOLS
from ..core.rag.knowledge_base import KnowledgeBase
from ..core.code.executor import CodeExecutor
from ..core.context import ContextCompressor, ConversationMemory
from ..core.observability import observe, update_current_span
from ..core.config import get_settings
from ..database.models import Message

class ChatService:
    def __init__(self, llm, knowledge_base, code_executor, conversation_memory=None):
        self.llm = llm
        self.kb = knowledge_base
        self.code_exec = code_executor
        self.memory = conversation_memory

        settings = get_settings()
        if settings.context_compression_enabled:
            self.compressor = ContextCompressor(
                llm_client=llm,
                budget_tokens=32000,
                keep_recent=8,
                summary_max_tokens=settings.context_compression_summary_max_tokens,
                trigger_ratio=0.8,
            )
        else:
            self.compressor = None

    async def _compress_history(
        self, history: list[dict] | None, user_id: int, conversation_id: int,
    ) -> tuple[list[dict], dict | None]:
        if self.compressor is None or not history:
            return (history or []), None

        s = get_settings()
        to_archive, recent, meta = self.compressor.compress_by_rounds(
            history, s.context_compression_trigger_rounds, s.context_compression_keep_rounds,
        )
        if to_archive is None:
            return history, None

        self.memory.index_history(to_archive, user_id, conversation_id)
        result = await self.compressor.compress(to_archive)
        summary = result.summary if result.was_compressed else self.compressor.fallback_summary(to_archive)

        compressed = [{"role": "system", "content": f"[对话历史摘要 共{len(to_archive)}条消息]\n{summary}"}]
        compressed.extend(recent)
        return compressed, meta

    @observe()
    async def chat_sse(self, user_id, message, conversation_id=0,
                        history=None, db_session=None, system_context=None,
                        use_rag=True, use_web=False):
        """SSE streaming with optional tool calling."""
        compressed_history, comp_meta = await self._compress_history(history, user_id, conversation_id)
        messages = compressed_history + [{"role": "user", "content": message}]
        if system_context:
            messages = [{"role": "system", "content": system_context}] + messages

        # Build tools: memory always on, knowledge + web are optional
        tools = [t for t in RAG_TOOLS if t["function"]["name"] == "search_memory"]
        if use_rag:
            tools.append([t for t in RAG_TOOLS if t["function"]["name"] == "search_knowledge"][0])
        if use_web:
            tools.append([t for t in RAG_TOOLS if t["function"]["name"] == "search_web"][0])
        tools = tools if tools else None
        resp = await self.llm.chat(messages, tools=tools)

        if resp["type"] == "tool_calls":
            seen = set()
            for tc in resp["tool_calls"]:
                if tc.function.name in seen:
                    continue
                seen.add(tc.function.name)
                name = tc.function.name
                args = json.loads(tc.function.arguments)
                query = args.get("query", message)

                label = "📚 正在检索知识库" if name == "search_knowledge" else "🧠 正在检索对话记忆"
                yield f'data: {{"event":"status","content":"{label}: {query}"}}\n\n'

                if name == "search_knowledge":
                    results = await self.kb.search(query, top_k=5)
                    if results:
                        yield 'data: {{"event":"status","content":"找到 {} 条相关知识"}}\n\n'.format(len(results))
                        tool_output = "\n\n".join(
                            f"[{r.source}] (score={r.score:.2f})\n{r.content[:1000]}"
                            for r in results
                        )
                        self._save_tool(db_session, user_id, conversation_id,
                            f"RAG 知识库检索: {query}", f"检索到 {len(results)} 条")
                    else:
                        yield f'data: {{"event":"status","content":"未找到相关知识"}}\n\n'
                        tool_output = "未找到相关知识。"
                elif name == "search_memory":
                    try:
                        mem_results = await self.memory.search(query, user_id=user_id, top_k=5)
                        mem_results = [r for r in mem_results if r.score > 0.3]
                        if mem_results:
                            yield f'data: {{"event":"status","content":"检索到 {len(mem_results)} 条对话记忆"}}\n\n'
                            tool_output = "\n\n".join(f"[conversation history] {r.content[:800]}" for r in mem_results[:5])
                        else:
                            yield f'data: {{"event":"status","content":"未找到相关对话记忆"}}\n\n'
                            tool_output = "未找到相关历史对话记忆。"
                    except Exception:
                        yield f'data: {{"event":"status","content":"记忆检索暂时不可用"}}\n\n'
                        tool_output = "记忆检索暂时不可用。"
                elif name == "search_web":
                    yield f'data: {{"event":"status","content":"🌐 联网搜索中..."}}\n\n'
                    try:
                        from ..core.config import get_settings
                        s = get_settings()
                        if s.tavily_api_key:
                            from tavily import TavilyClient
                            tv = TavilyClient(api_key=s.tavily_api_key)
                            resp = tv.search(query=query, max_results=5)
                            results = resp.get("results", [])
                            if results:
                                tool_output = "\n\n".join(
                                    f"[Web] {r['title']}\n{r['url']}\n{r['content'][:500]}"
                                    for r in results[:5]
                                )
                                yield f'data: {{"event":"status","content":"找到 {len(results)} 条网页"}}\n\n'
                            else:
                                tool_output = "未找到相关网页。"
                        else:
                            tool_output = "Tavily API key 未配置"
                    except Exception:
                        tool_output = "联网搜索暂时不可用。"
                else:
                    tool_output = f"Unknown tool: {name}"

                messages.append({
                    "role": "assistant", "content": None,
                    "tool_calls": [{"id": tc.id if hasattr(tc, 'id') else "", "type": "function",
                                    "function": {"name": name, "arguments": tc.function.arguments}}],
                })
                messages.append({"role": "tool", "tool_call_id": tc.id if hasattr(tc, 'id') else "", "content": tool_output})

        # Phase 2: stream final answer
        yield 'data: {"event":"status","content":"正在生成回答..."}\n\n'
        full = ""
        async for chunk in self.llm.chat_stream(messages):
            # Strip XML tool_call artifacts that the model may output
            clean = chunk
            if '<tool_calls>' in clean or '<invoke' in clean or '||DSML||' in clean:
                continue
            full += clean
            yield f'data: {{"event":"answer","content":{json.dumps(clean)}}}\n\n'

        yield 'data: {"event":"done"}\n\n'

    def _save_tool(self, db_session, user_id, conv_id, tool_call, tool_result):
        if not db_session or not conv_id:
            return
        try:
            db_session.add(Message(user_id=user_id, conversation_id=conv_id, role="tool", content=tool_call))
            db_session.add(Message(user_id=user_id, conversation_id=conv_id, role="tool_result", content=tool_result))
        except Exception:
            pass
