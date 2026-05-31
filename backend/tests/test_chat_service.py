"""Tests for ChatService."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.services.chat_service import ChatService


class TestChatService:
    @pytest.fixture
    def svc(self, mock_llm):
        kb = MagicMock()
        kb.search = AsyncMock(return_value=[])
        kb.search_memory = AsyncMock(return_value=[])

        mem = MagicMock()
        mem.search = AsyncMock(return_value=[])
        mem.add_chunks = MagicMock()

        executor = MagicMock()
        executor.execute = AsyncMock(return_value={"stdout": "", "stderr": "", "exit_code": 0, "images": []})

        return ChatService(llm=mock_llm, knowledge_base=kb, code_executor=executor, conversation_memory=mem)

    @pytest.mark.asyncio
    async def test_chat_basic(self, svc):
        result = await svc.chat(user_id=1, message="Hello", conversation_id=1, history=[])
        assert "response" in result
        assert isinstance(result["response"], str)
        assert len(result["response"]) > 0

    @pytest.mark.asyncio
    async def test_chat_compresses_long_history(self, svc, mock_llm):
        mock_llm.raw_chat = AsyncMock(return_value="Mock summary.")
        long_hist = []
        for i in range(40):
            long_hist.append({"role": "user", "content": f"Q{i}: " + "x" * 100})
            long_hist.append({"role": "assistant", "content": f"A{i}: " + "y" * 100})
        result = await svc.chat(user_id=1, message="Query", conversation_id=1, history=long_hist)
        assert "response" in result

    @pytest.mark.asyncio
    async def test_agent_chat(self, svc):
        result = await svc.chat(user_id=1, message="Hello", conversation_id=1, history=[], use_agent=True)
        assert "response" in result
        assert isinstance(result["response"], str)
