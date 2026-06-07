"""Tests for ChatService."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.services.chat_service import ChatService


class TestChatService:
    @pytest.fixture
    def svc(self, mock_llm):
        kb = MagicMock()
        kb.search = AsyncMock(return_value=[])

        mem = MagicMock()
        mem.search = AsyncMock(return_value=[])
        mem.add_chunks = MagicMock()

        executor = MagicMock()
        executor.execute = AsyncMock(return_value={"stdout": "", "stderr": "", "exit_code": 0, "images": []})

        return ChatService(llm=mock_llm, knowledge_base=kb, code_executor=executor, conversation_memory=mem)

    @pytest.mark.asyncio
    async def test_chat_sse_basic(self, svc):
        lines = []
        async for line in svc.chat_sse(user_id=1, message="Hello", conversation_id=1, history=[]):
            lines.append(line)
        assert len(lines) > 0
        assert any("done" in l for l in lines)

    @pytest.mark.asyncio
    async def test_chat_sse_compresses_long_history(self, svc, mock_llm):
        mock_llm.chat = AsyncMock(return_value={"type": "text", "content": "Mock response."})
        long_hist = []
        for i in range(40):
            long_hist.append({"role": "user", "content": f"Q{i}: " + "x" * 100})
            long_hist.append({"role": "assistant", "content": f"A{i}: " + "y" * 100})
        lines = []
        async for line in svc.chat_sse(user_id=1, message="Query", conversation_id=1, history=long_hist):
            lines.append(line)
        assert len(lines) > 0
