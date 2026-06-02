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

        if not result.get("stderr") or result.get("exit_code", -1) == 0:
            return {"code": code, "result": result}

        # Debug + retry loop (up to 3 attempts)
        attempts = []
        current_code = code
        for i in range(3):
            debug_info = self.debugger.analyze_error(result["stderr"])
            fixed_code = await self.debugger.fix_code(current_code, result["stderr"])
            fixed_result = await self.executor.execute(fixed_code, language)

            attempts.append({
                "code": fixed_code,
                "result": fixed_result,
                "error_type": debug_info.error_type,
                "suggestion": debug_info.suggestion,
            })

            if not fixed_result.get("stderr") or fixed_result.get("exit_code", -1) == 0:
                return {
                    "code": fixed_code,
                    "result": fixed_result,
                    "original_code": code,
                    "original_result": result,
                    "fix_attempts": len(attempts),
                    "attempts": attempts,
                }

            current_code = fixed_code
            result = fixed_result

        return {
            "code": attempts[-1]["code"],
            "result": attempts[-1]["result"],
            "original_code": code,
            "original_result": result,
            "fix_attempts": len(attempts),
            "attempts": attempts,
            "error": "Code still has errors after 3 fix attempts",
        }
