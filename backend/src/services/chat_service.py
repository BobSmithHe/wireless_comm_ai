from typing import AsyncIterator
from ..core.llm.deepseek_client import DeepSeekClient
from ..core.rag.knowledge_base import KnowledgeBase
from ..core.agent.agent_core import AgentCore
from ..core.agent.task_planner import TaskPlanner
from ..core.code.executor import CodeExecutor
from ..core.context import ContextCompressor, ConversationMemory
from ..core.observability import observe, update_current_span
from ..config.settings import get_settings
from ..database.models import Message

_planner = TaskPlanner()


class ChatService:
    def __init__(self, llm, knowledge_base, code_executor, conversation_memory=None):
        self.llm = llm
        self.kb = knowledge_base
        self.code_exec = code_executor
        self.memory = conversation_memory  # ConversationMemory (compressed history)
        self.agent = AgentCore(llm, knowledge_base, code_executor)

        settings = get_settings()
        if settings.context_compression_enabled:
            self.compressor = ContextCompressor(
                llm_client=llm,
                budget_tokens=settings.context_compression_budget_tokens,
                keep_recent=settings.context_compression_keep_recent,
                summary_max_tokens=settings.context_compression_summary_max_tokens,
                trigger_ratio=settings.context_compression_trigger_ratio,
            )
        else:
            self.compressor = None

    async def _compress_history(
        self, history: list[dict] | None, user_id: int, conversation_id: int,
    ) -> tuple[list[dict], dict | None]:
        """Compress history if over budget. Returns (messages, compression_metadata).

        Compressed messages are indexed into the vector DB keyed by conversation,
        so future queries against the same conversation can retrieve them.
        """
        if self.compressor is None or not history:
            return (history or []), None
        result = await self.compressor.compress(history)
        if not result.was_compressed:
            return history, None

        if result.compressed_messages:
            self._index_compressed_history(result.compressed_messages, user_id, conversation_id)

        return result.messages, {
            "compression_was_compressed": True,
            "compression_original_tokens": result.original_token_count,
            "compression_compressed_tokens": result.compressed_token_count,
            "compression_kept_messages": result.kept_message_count,
            "compression_compressed_messages": result.compressed_message_count,
            "compression_reduction_ratio": result.reduction_ratio,
        }

    def _index_compressed_history(
        self, messages: list[dict], user_id: int, conversation_id: int,
    ) -> None:
        """Index compressed messages into vector DB, scoped to user + conversation.

        Each compression adds NEW chunks — old chunks from previous compressions
        remain searchable. The source tag carries the conversation_id for filtering.
        """
        try:
            source_tag = f"compressed_history:{conversation_id}"
            chunks = []
            for m in messages:
                role = m.get("role", "user")
                content = m.get("content", "")
                if content.strip():
                    chunks.append(f"[{role}]: {content[:2000]}")
            if chunks:
                self.memory.add_chunks(
                    texts=chunks,
                    metadatas=[{
                        "source": source_tag,
                        "type": "conversation_memory",
                        "user_id": user_id,
                        "conversation_id": conversation_id,
                    } for _ in chunks],
                )
        except Exception:
            pass

    @observe()
    async def chat(
        self, user_id, message, conversation_id=0, history=None,
        use_agent=False, db_session=None, system_context=None,
    ) -> dict:
        if use_agent:
            return await self._agent_chat(user_id, message, conversation_id, history, db_session)

        # ---- Retrieve compressed conversation history from vector DB ----
        history_chunks = await self.memory.search(message, top_k=2)
        source_tag = f"compressed_history:{conversation_id}"
        relevant_history = [r for r in history_chunks if r.score > 0.3 and r.source == source_tag]

        if relevant_history:
            self._save_tool(db_session, user_id, conversation_id,
                "历史检索", f"检索到 {len(relevant_history)} 条相关对话片段")

        # Build messages
        compressed_history, comp_meta = await self._compress_history(history, user_id, conversation_id)
        context_parts = []
        if relevant_history:
            context_parts.append("[Relevant Conversation History]\n" + "\n".join(r.content[:300] for r in relevant_history))
        context = "\n\n".join(context_parts)
        messages = compressed_history + [{"role": "user", "content": message}]
        if system_context:
            messages = [{"role": "system", "content": system_context}] + messages
        if context:
            messages = [{"role": "system", "content": context}] + messages

        response = await self.llm.chat(messages)

        update_current_span(
            output=response,
            metadata={
                "use_agent": False,
                "history_hits": len(relevant_history),
                **(comp_meta or {}),
            },
        )
        return {"response": response, "sources": []}

    @observe()
    async def _agent_chat(self, user_id, message, conv_id, history, db_session):
        """Agent mode with full tool recording."""
        tasks = _planner.plan(message)
        task_desc = "\n".join(f"{i+1}. [{t.task_type.value}] {t.description}" for i, t in enumerate(tasks))
        self._save_tool(db_session, user_id, conv_id,
            f"Agent 任务规划\n查询: {message[:100]}",
            f"拆解为 {len(tasks)} 个子任务:\n{task_desc}")

        # Compressed conversation history (passive injection — always relevant)
        history_chunks = await self.memory.search(message, top_k=2)
        source_tag = f"compressed_history:{conv_id}"
        relevant_history = [r for r in history_chunks if r.score > 0.3 and r.source == source_tag]
        if relevant_history:
            self._save_tool(db_session, user_id, conv_id,
                "Agent 历史检索", f"检索到 {len(relevant_history)} 条相关历史对话片段")

        compressed_history, comp_meta = await self._compress_history(history, user_id, conv_id)
        result = await self.agent.run(user_id, message, compressed_history)

        update_current_span(
            output=result,
            metadata={
                "use_agent": True,
                "num_tasks": len(tasks),
                "history_hits": len(relevant_history),
                **(comp_meta or {}),
            },
        )
        return result

    @observe()
    async def chat_stream(
        self, user_id, message, conversation_id=0, history=None, db_session=None,
    ) -> AsyncIterator[str]:
        history_chunks = await self.memory.search(message, top_k=2)
        source_tag = f"compressed_history:{conversation_id}"
        relevant_history = [r for r in history_chunks if r.score > 0.3 and r.source == source_tag]

        if relevant_history and db_session:
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
        """Add tool messages to the DB session (committed later by caller)."""
        if not db_session or not conv_id:
            return
        try:
            db_session.add(Message(user_id=user_id, conversation_id=conv_id, role="tool", content=tool_call))
            db_session.add(Message(user_id=user_id, conversation_id=conv_id, role="tool_result", content=tool_result))
        except Exception:
            pass
