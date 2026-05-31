from typing import AsyncIterator
from openai import AsyncOpenAI
from .base_llm import BaseLLM
from ...config.settings import get_settings
from ..observability import observe, update_current_generation

settings = get_settings()

SYSTEM_PROMPT = """You are a wireless communications AI assistant. Your expertise covers:
- 4G LTE / 5G NR physical layer and protocols
- OFDM, MIMO, beamforming, channel coding (LDPC, Polar)
- Channel estimation, equalization, synchronization
- Wireless standards: 3GPP, IEEE 802.11 (WiFi), DVB
- Digital signal processing for communications

When answering:
1. Be precise about technical details and formulas
2. Reference applicable 3GPP spec sections when relevant
3. Provide Python/numpy code examples when helpful
4. Acknowledge uncertainty if a question is beyond your knowledge"""


class DeepSeekClient(BaseLLM):
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.client = AsyncOpenAI(
            api_key=api_key or settings.deepseek_api_key,
            base_url=base_url or settings.deepseek_base_url,
        )
        self.model = model or settings.deepseek_model

    @observe(as_type="generation")
    async def chat(self, messages: list[dict], **kwargs) -> str:
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
        temperature = kwargs.get("temperature", 0.3)
        max_tokens = kwargs.get("max_tokens", 4096)

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content or ""

        # Attach usage + model info to the langfuse span
        if response.usage:
            update_current_generation(
                output=content,
                model=self.model,
                model_parameters={
                    "temperature": str(temperature),
                    "max_tokens": str(max_tokens),
                },
                usage_details={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
            )
        return content

    @observe(as_type="generation")
    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
        temperature = kwargs.get("temperature", 0.3)
        max_tokens = kwargs.get("max_tokens", 4096)

        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        collected: list[str] = []
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                collected.append(chunk.choices[0].delta.content)
                yield chunk.choices[0].delta.content

        full_text = "".join(collected)
        update_current_generation(
            output=full_text,
            model=self.model,
            model_parameters={
                "temperature": str(temperature),
                "max_tokens": str(max_tokens),
            },
            usage_details={
                "output_tokens_approx": len(full_text.split()),
            },
            metadata={"stream": True},
        )

    @observe(as_type="generation")
    async def raw_chat(self, messages: list[dict], **kwargs) -> str:
        """Chat WITHOUT the wireless-comm system prompt. For meta-tasks (summarisation etc.)."""
        temperature = kwargs.get("temperature", 0.3)
        max_tokens = kwargs.get("max_tokens", 4096)

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content or ""

        if response.usage:
            update_current_generation(
                output=content,
                model=self.model,
                model_parameters={
                    "temperature": str(temperature),
                    "max_tokens": str(max_tokens),
                },
                usage_details={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                metadata={"raw": True},
            )
        return content

    @observe(as_type="embedding")
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Use DeepSeek-compatible embedding (falls back to simple TF-IDF if unavailable)."""
        try:
            response = await self.client.embeddings.create(
                model="deepseek-embedding", input=texts
            )
            result = [d.embedding for d in response.data]
            update_current_generation(
                output={"num_texts": len(texts), "dim": len(result[0]) if result else 0},
                metadata={"model": "deepseek-embedding", "fallback": False},
            )
            return result
        except Exception:
            fallback = self._fallback_embed(texts)
            update_current_generation(
                metadata={"model": "fallback-ngram", "fallback": True},
            )
            return fallback

    def _fallback_embed(self, texts: list[str]) -> list[list[float]]:
        """Simple character n-gram based embedding fallback."""
        import hashlib
        embeddings = []
        for text in texts:
            vec = [0.0] * 128
            for i, ch in enumerate(text[:512]):
                h = int(hashlib.md5(ch.encode()).hexdigest()[:2], 16)
                vec[h % 128] += 1.0
            norm = sum(v**2 for v in vec) ** 0.5 or 1.0
            embeddings.append([v / norm for v in vec])
        return embeddings
