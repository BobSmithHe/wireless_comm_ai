"""Shared fixtures for all tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_llm():
    """A mock LLM client that returns preset responses."""
    llm = MagicMock()
    llm.chat = AsyncMock(return_value={"type": "text", "content": "Mock LLM response."})
    llm.raw_chat = AsyncMock(return_value="Mock raw response.")
    async def _mock_stream(*args, **kwargs):
        for c in ["chunk1", "chunk2"]:
            yield c
    llm.chat_stream = _mock_stream
    llm.embed = AsyncMock(return_value=[[0.1] * 1024])
    return llm


@pytest.fixture
def mock_db():
    """A mock SQLAlchemy session."""
    return MagicMock()


@pytest.fixture
def sample_messages():
    """A typical conversation history."""
    return [
        {"role": "user", "content": "What is OFDM?"},
        {"role": "assistant", "content": "OFDM is a modulation technique..."},
        {"role": "user", "content": "Explain subcarriers."},
        {"role": "assistant", "content": "Subcarriers are orthogonal frequency..."},
    ]
