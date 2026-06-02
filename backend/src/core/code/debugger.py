"""
Code Debugger - analyzes execution errors and suggests fixes.
"""
import re
from dataclasses import dataclass


def _extract_code(text: str) -> str:
    """Extract code from LLM response — handles markdown blocks and raw code."""
    m = re.search(r"```(?:\w+)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            return parts[1].strip()
    return text.strip()


@dataclass
class DebugResult:
    has_error: bool
    error_type: str
    error_line: int | None
    suggestion: str
    fixed_code: str | None = None


class CodeDebugger:
    def __init__(self, llm_client):
        self.llm = llm_client

    def analyze_error(self, stderr: str) -> DebugResult:
        """Static analysis of Python traceback to identify error type and location."""
        if not stderr.strip():
            return DebugResult(has_error=False, error_type="", error_line=None, suggestion="")

        lines = stderr.strip().split("\n")
        error_type = ""
        error_line = None

        for line in reversed(lines):
            if "Error" in line:
                import re
                m = re.match(r"(\w+Error)", line.strip())
                if m:
                    error_type = m.group(1)
            if 'line' in line.lower() and 'File' in line:
                import re
                m = re.search(r"line (\d+)", line)
                if m:
                    error_line = int(m.group(1))

        suggestion = self._get_suggestion(error_type, stderr)
        return DebugResult(
            has_error=True,
            error_type=error_type,
            error_line=error_line,
            suggestion=suggestion,
        )

    def _get_suggestion(self, error_type: str, stderr: str) -> str:
        suggestions = {
            "NameError": "Check for undefined variables or typos in variable/function names.",
            "TypeError": "Verify argument types match the function signature.",
            "ValueError": "Check if input values are in the expected range/format.",
            "IndexError": "Array/list index is out of bounds. Check array sizes.",
            "KeyError": "Dictionary key not found. Use .get() with a default value.",
            "ImportError": "Missing module. Install it with pip or check the import name.",
            "AttributeError": "Object doesn't have the accessed attribute. Check the object type.",
            "ZeroDivisionError": "Division by zero. Add a guard check for zero denominators.",
            "SyntaxError": "Syntax error. Check for missing colons, brackets, or indentation issues.",
        }
        for err_type, suggestion in suggestions.items():
            if err_type in error_type:
                return suggestion
        return f"Error: {error_type}. Review the code around the error location."

    async def fix_code(self, code: str, stderr: str) -> str:
        """Use LLM to fix the code based on the error."""
        prompt = f"""The following Python code has an error. Fix it.

=== CODE ===
{code}

=== ERROR ===
{stderr}

Return ONLY the corrected complete code. No explanations."""

        resp = await self.llm.chat([{"role": "user", "content": prompt}])
        return _extract_code(resp["content"])
