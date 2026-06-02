import json
from typing import AsyncIterator
from openai import AsyncOpenAI
from ...config.settings import get_settings
from ..observability import observe, update_current_generation

settings = get_settings()

SYSTEM_PROMPT = """You are a wireless communications AI assistant. Your expertise covers:
- 4G LTE / 5G NR physical layer and protocols
- OFDM, MIMO, beamforming, channel coding (LDPC, Polar)
- Channel estimation, equalization, synchronization
- Wireless standards: 3GPP, IEEE 802.11 (WiFi), DVB
- Digital signal processing for communications

You have two tools:
1. search_knowledge(query) — search the wireless communications knowledge base (3GPP specs, algorithms, protocols)
2. search_memory(query) — search past conversation history that may have been compressed/summarised

When to use search_knowledge: technical questions needing authoritative references.
When to use search_memory: when the user refers to something discussed earlier in the conversation
that you don't fully recall, or asks about a previous topic.
Do NOT use either tool for greetings, simple explanations from your own knowledge, or chitchat.

Output format — ALWAYS use standard Markdown:
1. Use # for top-level headings, ## for sub-headings
2. Use $$...$$ for display math, $...$ for inline math (KaTeX compatible)
3. Use ```language for code blocks with language tag
4. Use standard Markdown tables: | col | col |\n|---|---|
5. Do NOT output HTML tags, XML tags, or JSON
6. Be precise about technical details and formulas"""

RAG_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "搜索无线通信专业知识库（3GPP规范、算法细节、协议流程等权威资料）。当用户提出技术问题时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索查询词"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "搜索之前对话中被压缩/总结的历史记忆。当用户提到之前讨论过但你不确定的内容时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索查询词"},
                },
                "required": ["query"],
            },
        },
    },
]


class DeepSeekClient():
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
    async def chat(
        self, messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> dict:
        """Send messages, optionally with tool definitions.

        Returns:
            {"type": "text", "content": "...", "usage": {...}}
            {"type": "tool_calls", "tool_calls": [...], "usage": {...}}
        """
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
        temperature = kwargs.get("temperature", 0.3)
        max_tokens = kwargs.get("max_tokens", 4096)

        params = dict(
            model=self.model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"
            params["extra_body"] = {"thinking": {"type": "disabled"}}

        response = await self.client.chat.completions.create(**params)
        msg = response.choices[0].message

        usage_info = {}
        if response.usage:
            usage_info = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        if msg.tool_calls:
            update_current_generation(
                output="[tool_calls]",
                model=self.model,
                model_parameters={"temperature": str(temperature), "max_tokens": str(max_tokens)},
                usage_details=usage_info,
                metadata={"tool_calls": [tc.function.name for tc in msg.tool_calls]},
            )
            return {
                "type": "tool_calls",
                "tool_calls": msg.tool_calls,
                "usage": usage_info,
            }

        content = msg.content or ""
        update_current_generation(
            output=content,
            model=self.model,
            model_parameters={"temperature": str(temperature), "max_tokens": str(max_tokens)},
            usage_details=usage_info,
        )
        return {"type": "text", "content": content, "usage": usage_info}

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
            model_parameters={"temperature": str(temperature), "max_tokens": str(max_tokens)},
            usage_details={"output_tokens_approx": len(full_text.split())},
            metadata={"stream": True},
        )

    @observe(as_type="generation")
    async def raw_chat(self, messages: list[dict], **kwargs) -> str:
        """Chat WITHOUT the wireless-comm system prompt. For meta-tasks."""
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
                model_parameters={"temperature": str(temperature), "max_tokens": str(max_tokens)},
                usage_details={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                metadata={"raw": True},
            )
        return content
