"""
Agent Core - orchestrates task planning, tool execution, and response synthesis.
"""
import asyncio
from .task_planner import TaskPlanner, SubTask, TaskType
from .tool_executor import ToolExecutor, ToolRegistry, ToolResult
from ..observability import observe, update_current_span


class AgentCore:
    def __init__(self, llm_client, knowledge_base, code_executor):
        self.llm = llm_client
        self.kb = knowledge_base
        self.code_exec = code_executor
        self.planner = TaskPlanner()

        self.tool_registry = ToolRegistry()
        self.tool_executor = ToolExecutor(self.tool_registry)
        self._register_tools()

    def _register_tools(self) -> None:
        self.tool_registry.register("search_knowledge", self._tool_search_knowledge)
        self.tool_registry.register("search_memory", self._tool_search_memory)
        self.tool_registry.register("execute_code", self._tool_execute_code)

    @observe(as_type="tool")
    async def _tool_search_knowledge(self, query: str, top_k: int = 5) -> list[dict]:
        results = await self.kb.search(query, top_k)
        return [{"content": r.content, "score": r.score, "source": r.source} for r in results]

    @observe(as_type="tool")
    async def _tool_search_memory(self, query: str, user_id: int, limit: int = 5) -> list[dict]:
        return []

    @observe(as_type="tool")
    async def _tool_execute_code(self, code: str, language: str = "python") -> dict:
        result = await self.code_exec.execute(code, language)
        return {"stdout": result.get("stdout", ""), "stderr": result.get("stderr", ""), "exit_code": result.get("exit_code", -1)}

    @observe(as_type="agent")
    async def run(
        self,
        user_id: int,
        query: str,
        conversation_history: list[dict] | None = None,
    ) -> dict:
        """Full agent execution cycle."""
        conversation_history = conversation_history or []

        # Step 1: Plan
        sub_tasks = self.planner.plan(query)

        # Step 2: Execute each sub-task via registered tools (traced as tool spans)
        task_results: list[ToolResult] = []
        knowledge_context = ""

        for task in sub_tasks:
            if task.task_type == TaskType.KNOWLEDGE_LOOKUP:
                kb_results = await self._tool_search_knowledge(query, top_k=3)
                if kb_results:
                    knowledge_context = "\n\n".join(
                        f"[{r['source']}] (score={r['score']:.2f})\n{r['content'][:800]}"
                        for r in kb_results
                    )

            elif task.task_type == TaskType.CODE_GENERATE:
                code = await self._generate_code(query, knowledge_context)
                task_results.append(ToolResult(success=True, output=code))

            elif task.task_type == TaskType.CODE_EXECUTE:
                prev_code = None
                for tr in task_results:
                    if tr.success and tr.output:
                        prev_code = tr.output
                        break
                if prev_code:
                    exec_result = await self._tool_execute_code(prev_code, "python")
                    task_results.append(ToolResult(
                        success=exec_result.get("exit_code", -1) == 0,
                        output=exec_result,
                    ))

        # Step 3: Synthesize final response
        messages = conversation_history + [{"role": "user", "content": query}]

        if knowledge_context:
            messages.insert(-1, {"role": "system", "content": f"Use this knowledge base context:\n{knowledge_context}"})

        response = await self.llm.chat(messages)

        update_current_span(
            output=response,
            metadata={
                "num_sub_tasks": len(sub_tasks),
                "has_knowledge": bool(knowledge_context),
            },
        )

        return {"response": response, "sub_tasks": len(sub_tasks), "knowledge_sources": bool(knowledge_context)}

    @observe(as_type="generation")
    async def _generate_code(self, query: str, context: str) -> str:
        prompt = f"""Generate Python code for this wireless communication task: {query}

Context from knowledge base:
{context[:1500] if context else "No additional context available."}

Requirements:
- Use numpy, scipy, matplotlib as needed
- Include clear comments
- Make it runnable standalone
- Handle edge cases
- Output results with print() or matplotlib plots

Return ONLY the Python code, no explanations."""

        code = await self.llm.chat([{"role": "user", "content": prompt}])
        if code.startswith("```"):
            lines = code.split("\n")
            code = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return code
