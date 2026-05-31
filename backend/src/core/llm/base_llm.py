from abc import ABC, abstractmethod
from typing import AsyncIterator


class BaseLLM(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> str:
        """Send messages and get a complete response."""
        ...

    @abstractmethod
    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        """Send messages and get a streaming response chunk by chunk."""
        ...

    @abstractmethod
    async def raw_chat(self, messages: list[dict], **kwargs) -> str:
        """Send messages WITHOUT any system prompt. Caller controls all messages.

        Used for meta-tasks like context compression where the domain-specific
        system prompt would interfere.
        """
        ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        ...
