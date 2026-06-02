import json
from typing import AsyncIterator
from ..core.llm.deepseek_client import DeepSeekClient, RAG_TOOLS
from ..core.rag.knowledge_base import KnowledgeBase
from ..core.code.executor import CodeExecutor
from ..core.context import ContextCompressor, ConversationMemory
from ..core.observability import observe, update_current_span
from ..config.settings import get_settings
from ..database.models import Message

MAX_TOOL_ROUNDS = 3


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
        """Round-based compression: at N rounds, keep last K, archive & compress the rest."""
        if self.compressor is None or not history:
            return (history or []), None

        s = get_settings()
        trigger_count = max(s.context_compression_trigger_rounds, 4)
        keep_count = min(s.context_compression_keep_rounds, trigger_count // 2)

        # Count total messages
        if len(history) < trigger_count:
            return history, None

        # Split: archive first N-keep messages, keep last keep messages
        to_archive = history[:-keep_count] if keep_count > 0 else history
        recent = history[-keep_count:] if keep_count > 0 else []

        if not to_archive:
            return history, None

        # Store full old messages in Milvus for later retrieval
        self._index_compressed_history(to_archive, user_id, conversation_id)

        # Compress old messages into a summary for immediate context
        result = await self.compressor.compress(to_archive)
        summary = result.summary if result.was_compressed else self._fallback_summary(to_archive)

        compressed = [{"role": "system", "content": f"[对话历史摘要 共{len(to_archive)}条消息]\n{summary}"}]
        compressed.extend(recent)

        return compressed, {
            "compression_was_compressed": True,
            "compression_archived_msgs": len(to_archive),
            "compression_kept_msgs": len(recent),
            "total_msgs": len(history),
        }

    def _fallback_summary(self, messages: list[dict]) -> str:
        """Simple concatenation when LLM compression is unavailable."""
        parts = []
        for m in messages[:20]:
            content = m.get("content", "")
            parts.append(f"[{m.get('role', '?')}]: {content[:200]}")
        return "\n".join(parts)

    def _index_compressed_history(
        self, messages: list[dict], user_id: int, conversation_id: int,
    ) -> None:
        try:
            source_tag = f"compressed_history:{conversation_id}"
            chunks = []
            for m in messages:
                role = m.get("role", "user")
                content = m.get("content", "")
                if content.strip():
                    chunks.append(f"[{role}]: {content[:2000]}")
            if chunks:
                ids = self.memory.add_chunks(
                    texts=chunks,
                    metadatas=[{
                        "source": source_tag,
                        "type": "conversation_memory",
                        "user_id": user_id,
                        "conversation_id": conversation_id,
                    } for _ in chunks],
                )
                from ..utils.logger import logger
                logger.info(f"Memory indexed: {len(ids)} chunks for conv {conversation_id}")
        except Exception as e:
            from ..utils.logger import logger
            logger.warning(f"Memory index failed for conv {conversation_id}: {e}")

    # ------------------------------------------------------------------
    # Core chat — LLM-driven tool calling (RAG search_knowledge)
    # ------------------------------------------------------------------

    @observe()
    async def chat(
        self, user_id, message, conversation_id=0, history=None,
        db_session=None, system_context=None,
    ) -> dict:
        # Build initial messages: compressed history + user query
        compressed_history, comp_meta = await self._compress_history(history, user_id, conversation_id)
        messages = compressed_history + [{"role": "user", "content": message}]
        if system_context:
            messages = [{"role": "system", "content": system_context}] + messages

        sources = []
        tool_rounds = 0
        relevant_history = []
        for _ in range(MAX_TOOL_ROUNDS):
            resp = await self.llm.chat(messages, tools=RAG_TOOLS)

            if resp["type"] == "text":
                update_current_span(
                    output=resp["content"],
                    metadata={
                        "tool_rounds": tool_rounds,
                        "history_hits": len(relevant_history),
                        **(comp_meta or {}),
                    },
                )
                return {"response": resp["content"], "sources": sources}

            # Process tool calls — only first to avoid duplicate searches
            tc_active = resp["tool_calls"][:1]
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in tc_active
                ],
            })

            for tc in tc_active:
                tool_rounds += 1
                if tc.function.name == "search_knowledge":
                    args = json.loads(tc.function.arguments)
                    query = args.get("query", message)
                    results = await self.kb.search(query, top_k=3)

                    if results:
                        sources = [{"content": r.content[:200], "score": r.score, "source": r.source} for r in results]
                        tool_output = "\n\n".join(
                            f"[{r.source}] (score={r.score:.2f})\n{r.content[:1000]}"
                            for r in results
                        )
                        previews = "\n".join(
                            f"[{i+1}] {r.content[:120]}..."
                            for i, r in enumerate(results[:3])
                        )
                        self._save_tool(db_session, user_id, conversation_id,
                            f"RAG 知识库检索: {query}",
                            f"检索到 {len(results)} 条:\n{previews}")
                    else:
                        tool_output = "未找到相关知识。"
                        self._save_tool(db_session, user_id, conversation_id,
                            f"RAG 知识库检索: {query}", "无结果")

                elif tc.function.name == "search_memory":
                    args = json.loads(tc.function.arguments)
                    query = args.get("query", message)
                    try:
                        mem_results = await self.memory.search(query, user_id=user_id, top_k=5)
                        mem_results = [r for r in mem_results if r.score > 0.3]
                        source_tag = f"compressed_history:{conversation_id}"
                        same_conv = [r for r in mem_results if r.source == source_tag]
                        other_conv = [r for r in mem_results if r.source != source_tag]
                        mem_results = same_conv + other_conv
                        if mem_results:
                            relevant_history = mem_results
                            parts = []
                            for r in mem_results[:5]:
                                label = "" if r.source == source_tag else f" [对话{r.source.split(':')[-1]}]"
                                parts.append(f"[conversation history{label}] {r.content[:800]}")
                            tool_output = "\n\n".join(parts)
                            self._save_tool(db_session, user_id, conversation_id,
                                f"记忆检索: {query}",
                                f"检索到 {len(mem_results)} 条(本对话{len(same_conv)}条, 跨对话{len(other_conv)}条)")
                        else:
                            tool_output = "未找到相关历史对话记忆。"
                    except Exception:
                        tool_output = "记忆检索暂时不可用。"
                else:
                    tool_output = f"Unknown tool: {tc.function.name}"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_output,
                })

        # Final response after tool rounds exhausted
        resp = await self.llm.chat(messages, tools=None)
        final_text = resp["content"] if resp["type"] == "text" else "（处理超时，请重试）"
        update_current_span(
            output=final_text,
            metadata={
                "tool_rounds": tool_rounds,
                "history_hits": len(relevant_history),
                **(comp_meta or {}),
            },
        )
        return {"response": final_text, "sources": sources}

    # ------------------------------------------------------------------
    # Streaming chat (no tool calling — tools need non-streaming flow)
    # ------------------------------------------------------------------

    @observe()
    async def chat_stream(
        self, user_id, message, conversation_id=0, history=None, db_session=None,
    ) -> AsyncIterator[str]:
        try:
            history_chunks = await self.memory.search(message, top_k=2)
            source_tag = f"compressed_history:{conversation_id}"
            relevant_history = [r for r in history_chunks if r.score > 0.3 and r.source == source_tag]
        except Exception:
            history_chunks, relevant_history = [], []
            self._save_tool(db_session, user_id, conversation_id,
                "历史检索", f"检索到 {len(relevant_history)} 条相关对话片段")

        context_parts = []
        if relevant_history:
            context_parts.append("[Relevant Conversation History]\n" + "\n".join(r.content[:300] for r in relevant_history))
        context = "\n\n".join(context_parts)

        compressed_history, comp_meta = await self._compress_history(history, user_id, conversation_id)
        messages = compressed_history + [{"role": "user", "content": message}]
        if context:
            messages = [{"role": "system", "content": context}] + messages

        full_response = ""
        async for chunk in self.llm.chat_stream(messages):
            full_response += chunk
            yield chunk

        update_current_span(
            output=full_response,
            metadata={
                "stream": True,
                "history_hits": len(relevant_history),
                **(comp_meta or {}),
            },
        )

    def _save_tool(self, db_session, user_id, conv_id, tool_call, tool_result):
        if not db_session or not conv_id:
            return
        try:
            db_session.add(Message(user_id=user_id, conversation_id=conv_id, role="tool", content=tool_call))
            db_session.add(Message(user_id=user_id, conversation_id=conv_id, role="tool_result", content=tool_result))
        except Exception:
            pass
