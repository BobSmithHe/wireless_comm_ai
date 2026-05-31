"""Tests for ContextCompressor."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.core.context.context_compressor import (
    ContextCompressor, CompressionResult, _estimate_tokens,
)


class TestTokenEstimation:
    def test_empty(self):
        assert _estimate_tokens([]) == 0

    def test_short_message(self):
        msgs = [{"role": "user", "content": "Hello"}]
        tokens = _estimate_tokens(msgs)
        assert 2 <= tokens <= 15

    def test_long_message(self):
        msgs = [{"role": "user", "content": "x" * 1000}]
        tokens = _estimate_tokens(msgs)
        assert 100 <= tokens <= 300  # ~1000/4 + 4 overhead (chars, not bytes)


class TestCompressionResult:
    def test_reduction_ratio(self):
        r = CompressionResult(
            messages=[{"role": "user", "content": "test"}],
            was_compressed=True,
            original_token_count=1000,
            compressed_token_count=300,
        )
        assert r.reduction_ratio == 0.7

    def test_reduction_ratio_zero_original(self):
        r = CompressionResult(messages=[{"role": "user", "content": "test"}], original_token_count=0)
        assert r.reduction_ratio == 0.0


class TestCompress:
    @pytest.fixture
    def compressor(self):
        llm = MagicMock()
        llm.raw_chat = AsyncMock(return_value="Summary: user asked about OFDM.")
        return ContextCompressor(
            llm_client=llm,
            budget_tokens=200,
            keep_recent=2,
            summary_max_tokens=100,
            trigger_ratio=0.8,
        )

    @pytest.mark.asyncio
    async def test_no_compress_short_history(self, compressor):
        short = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = await compressor.compress(short)
        assert not result.was_compressed
        assert len(result.messages) == 2

    @pytest.mark.asyncio
    async def test_compress_long_history(self, compressor):
        long = []
        for i in range(20):
            long.append({"role": "user", "content": f"Q{i}: " + "signal processing " * 15})
            long.append({"role": "assistant", "content": f"A{i}: " + "wireless " * 15})
        result = await compressor.compress(long)
        assert result.was_compressed
        assert result.summary is not None
        assert len(result.summary) > 0
        # Keep most recent messages + summary
        assert len(result.messages) < len(long)
        # First message should be the summary
        assert "对话历史摘要" in result.messages[0]["content"]

    @pytest.mark.asyncio
    async def test_compress_saves_original_messages(self, compressor):
        long = []
        for i in range(20):
            long.append({"role": "user", "content": f"Q{i}: " + "x" * 100})
            long.append({"role": "assistant", "content": f"A{i}: " + "y" * 100})
        result = await compressor.compress(long)
        assert result.compressed_messages is not None
        assert len(result.compressed_messages) > 0

