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

        response = await self.llm.chat([{"role": "user", "content": prompt}])
        code = response
        if code.startswith("```"):
            lines = code.split("\n")
            code = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return code

    async def debug(self, code: str, error_message: str) -> str:
        prompt = f"""Fix this Python code that has an error.

CODE:
```python
{code}
```

ERROR:
{error_message}

Return ONLY the corrected code, no explanations."""

        response = await self.llm.chat([{"role": "user", "content": prompt}])
        fixed = response
        if fixed.startswith("```"):
            lines = fixed.split("\n")
            fixed = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return fixed
