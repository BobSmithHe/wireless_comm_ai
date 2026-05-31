from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ...services.code_service import CodeService
from ..dependencies import get_current_user, get_code_service

router = APIRouter(prefix="/api/code", tags=["code"])


class CodeExecuteRequest(BaseModel):
    code: str
    language: str = "python"
    stdin: str | None = None


class CodeGenerateRequest(BaseModel):
    description: str
    language: str = "python"


@router.post("/execute")
async def execute_code(
    req: CodeExecuteRequest,
    user=Depends(get_current_user),
    code_service: CodeService = Depends(get_code_service),
):
    result = await code_service.execute(req.code, req.language)
    if result.get("exit_code", -1) != 0:
        return {"success": False, **result}
    return {"success": True, **result}


@router.post("/generate")
async def generate_and_execute(
    req: CodeGenerateRequest,
    user=Depends(get_current_user),
    code_service: CodeService = Depends(get_code_service),
):
    result = await code_service.generate_and_execute(req.description, req.language)
    return result
