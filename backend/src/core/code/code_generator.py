import re


def _extract_code(text: str) -> str:
    """Extract code from LLM response — handles markdown blocks and raw code."""
    # Prefer fenced code blocks
    m = re.search(r"```(?:\w+)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Fallback: lines between ``` markers even if malformed
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            return parts[1].strip()
    return text.strip()


class CodeGenerator:
    """Generate wireless communication simulation code using LLM."""

    def __init__(self, llm_client):
        self.llm = llm_client

    async def generate(self, description: str, language: str = "python", context: str = "") -> str:
        prompt = f"""Generate {language} code for this wireless communication task:

{description}

{f'Context: {context}' if context else ''}

Requirements:
- The code should be complete and runnable
- Include necessary imports (numpy, scipy, matplotlib)
- Print results or generate plots as appropriate
- Follow PEP 8 style
- Handle typical edge cases"""

        resp = await self.llm.chat([{"role": "user", "content": prompt}])
        return _extract_code(resp["content"])

    async def debug(self, code: str, error_message: str) -> str:
        prompt = f"""Fix this Python code that has an error.

CODE:
```python
{code}
```

ERROR:
{error_message}

Return ONLY the corrected code, no explanations."""

        resp = await self.llm.chat([{"role": "user", "content": prompt}])
        return _extract_code(resp["content"])
