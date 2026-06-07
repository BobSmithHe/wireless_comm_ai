from typing import AsyncIterator
from openai import AsyncOpenAI
from ...core.config import get_settings
from ...core.observability import observe, update_current_generation

settings = get_settings()

from .prompts import SYSTEM_PROMPT


class DeepSeekClient:
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
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
        temperature = kwargs.get("temperature", 0.3)
        max_tokens = kwargs.get("max_tokens", 4096)

        params = dict(
            model=self.model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        params["extra_body"] = {"thinking": {"type": "disabled"}}
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"

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
            extra_body={"thinking": {"type": "disabled"}},
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
