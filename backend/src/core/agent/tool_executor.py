"""
Tool Executor - manages tool calling lifecycle.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ToolResult:
    success: bool
    output: Any
    error: str | None = None
    execution_time_ms: float = 0.0


class ToolRegistry:
    """Registry of callable tools available to the agent."""

    def __init__(self):
        self._tools: dict[str, callable] = {}

    def register(self, name: str, func: callable) -> None:
        self._tools[name] = func

    def get(self, name: str) -> callable | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def get_tool_descriptions(self) -> list[dict]:
        return [{"name": name, "description": func.__doc__ or ""} for name, func in self._tools.items()]


class ToolExecutor:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute(self, tool_name: str, **kwargs) -> ToolResult:
        import time

        func = self.registry.get(tool_name)
        if func is None:
            return ToolResult(success=False, output=None, error=f"Unknown tool: {tool_name}")

        start = time.time()
        try:
            result = await func(**kwargs) if hasattr(func, "__call__") else func(**kwargs)
            elapsed = (time.time() - start) * 1000
            return ToolResult(success=True, output=result, execution_time_ms=elapsed)
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return ToolResult(success=False, output=None, error=str(e), execution_time_ms=elapsed)
