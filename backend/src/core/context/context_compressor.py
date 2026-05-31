"""
Context Compressor — keeps LLM input within a token budget by summarising
older conversation turns into a compact summary via the LLM itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Token estimation — try tiktoken, fall back to character heuristic
# ---------------------------------------------------------------------------
try:
    import tiktoken

    _enc = tiktoken.get_encoding("cl100k_base")

    def _estimate_tokens(messages: list[dict]) -> int:
        total = 0
        for m in messages:
            text = f"role: {m['role']}\ncontent: {m['content']}"
            total += len(_enc.encode(text)) + 4  # +4 for chat-template framing
        return total

except ImportError:

    def _estimate_tokens(messages: list[dict]) -> int:  # type: ignore[no-redef]
        total = 0
        for m in messages:
            total += len(m.get("content", "")) // 4 + 4
        return total


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class CompressionResult:
    messages: list[dict]  # compressed message list ready for LLM
    was_compressed: bool = False
    original_token_count: int = 0
    compressed_token_count: int = 0
    summary: str | None = None
    compressed_messages: list[dict] = None  # the messages that were folded into summary
    kept_message_count: int = 0
    compressed_message_count: int = 0

    @property
    def reduction_ratio(self) -> float:
        if self.original_token_count == 0:
            return 0.0
        return round(1 - self.compressed_token_count / self.original_token_count, 3)


# ---------------------------------------------------------------------------
# ContextCompressor
# ---------------------------------------------------------------------------


class ContextCompressor:
    def __init__(
        self,
        llm_client,
        *,
        budget_tokens: int = 4000,
        keep_recent: int = 6,
        summary_max_tokens: int = 500,
        trigger_ratio: float = 0.8,
    ):
        self.llm = llm_client
        self.budget_tokens = budget_tokens
        self.keep_recent = keep_recent
        self.summary_max_tokens = summary_max_tokens
        self.trigger_ratio = trigger_ratio

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def compress(
        self,
        messages: list[dict],
        existing_summary: str | None = None,
    ) -> CompressionResult:
        """Compress *messages* if they exceed the token budget, else return as-is."""
        if not messages:
            return CompressionResult(messages=messages)

        estimated = _estimate_tokens(messages)
        threshold = int(self.budget_tokens * self.trigger_ratio)

        if estimated <= threshold:
            return CompressionResult(
                messages=messages,
                original_token_count=estimated,
                compressed_token_count=estimated,
            )

        # Split: older messages to compress, recent messages to keep
        keep_budget = self.budget_tokens // 2
        to_compress, recent = self._split(messages, keep_budget)

        if not to_compress:
            return CompressionResult(
                messages=messages,
                original_token_count=estimated,
                compressed_token_count=estimated,
            )

        # Generate summary via LLM
        summary = await self._summarise(to_compress, existing_summary)

        # Assemble compressed list
        compressed = [
            {
                "role": "system",
                "content": f"[对话历史摘要]\n{summary}",
            }
        ]
        compressed.extend(recent)

        compressed_tokens = _estimate_tokens(compressed)

        return CompressionResult(
            messages=compressed,
            was_compressed=True,
            original_token_count=estimated,
            compressed_token_count=compressed_tokens,
            summary=summary,
            kept_message_count=len(recent),
            compressed_message_count=len(to_compress),
            compressed_messages=to_compress,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _split(self, messages: list[dict], keep_budget: int) -> tuple[list[dict], list[dict]]:
        """Split messages into (to_compress, recent)."""
        recent: list[dict] = []
        recent_tokens = 0
        for m in reversed(messages):
            t = _estimate_tokens([m])
            if (
                len(recent) < self.keep_recent
                or recent_tokens + t <= keep_budget
            ):
                recent.insert(0, m)
                recent_tokens += t
            else:
                break
        split_at = len(messages) - len(recent)
        if split_at <= 0:
            return [], list(messages)
        return list(messages[:split_at]), recent

    async def _summarise(
        self, messages: list[dict], existing_summary: str | None
    ) -> str:
        """Ask the LLM to produce a compact summary of the given messages."""
        formatted = self._format_for_summary(messages)

        prompt_parts = [
            "Summarise the following conversation between a user and a wireless-communications AI assistant.",
            "Focus on: key technical questions asked, answers given, decisions made, code or formulas discussed.",
            "Keep it concise — target no more than {max_t} words. Use the same language as the conversation.",
        ]
        prompt = " ".join(part.format(max_t=self.summary_max_tokens // 4) for part in prompt_parts)

        if existing_summary:
            prompt += f"\n\n[Previous summary]\n{existing_summary}\n"
        prompt += f"\n\n--- Conversation to summarise ---\n{formatted}\n---\n\nSummary:"

        try:
            summary = await self.llm.raw_chat(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=self.summary_max_tokens,
            )
            return summary.strip()
        except Exception:
            # Fallback: simple concatenation of first sentence from each message
            fallback: list[str] = []
            for m in messages:
                content = m.get("content", "")
                first_sent = content.split(".")[0].split("\n")[0][:200]
                if first_sent.strip():
                    fallback.append(f"[{m['role']}]: {first_sent.strip()}")
            return "\n".join(fallback[:20])

    @staticmethod
    def _format_for_summary(messages: list[dict]) -> str:
        lines: list[str] = []
        for m in messages:
            role = m["role"].upper()
            content = m.get("content", "")[:2000]
            lines.append(f"[{role}]: {content}")
        return "\n\n".join(lines)
