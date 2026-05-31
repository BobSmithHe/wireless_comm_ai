"""Shared fixtures for all tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_llm():
    """A mock LLM client that returns preset responses."""
    llm = MagicMock()
    llm.chat = AsyncMock(return_value="Mock LLM response.")
    llm.raw_chat = AsyncMock(return_value="Mock raw response.")
    llm.chat_stream = AsyncMock(return_value=iter(["chunk1", "chunk2"]))
    llm.embed = AsyncMock(return_value=[[0.1] * 384])
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
