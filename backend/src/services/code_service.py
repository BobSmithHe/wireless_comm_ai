from ..core.code.executor import CodeExecutor
from ..core.code.code_generator import CodeGenerator
from ..core.code.debugger import CodeDebugger


class CodeService:
    def __init__(self, executor: CodeExecutor, code_generator: CodeGenerator, debugger: CodeDebugger):
        self.executor = executor
        self.generator = code_generator
        self.debugger = debugger

    async def execute(self, code: str, language: str = "python") -> dict:
        return await self.executor.execute(code, language)

    async def generate_and_execute(self, description: str, language: str = "python") -> dict:
        code = await self.generator.generate(description, language)
        result = await self.executor.execute(code, language)

        if result.get("stderr") and result.get("exit_code", -1) != 0:
            debug_info = self.debugger.analyze_error(result["stderr"])
            fixed_code = await self.debugger.fix_code(code, result["stderr"])
            fixed_result = await self.executor.execute(fixed_code, language)
            return {
                "original_code": code,
                "original_result": result,
                "error_analysis": {
                    "type": debug_info.error_type,
                    "suggestion": debug_info.suggestion,
                },
                "fixed_code": fixed_code,
                "fixed_result": fixed_result,
            }

        return {"code": code, "result": result}
