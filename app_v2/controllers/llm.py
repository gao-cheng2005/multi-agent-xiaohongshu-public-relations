"""大模型配置接口。

设置页"大模型设置"调用的接口：查看可选模型清单、查看当前生效模型与运行状态、切换模型。
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..services.llm_config_service import LLMConfigService

router = APIRouter()


class ModelUpdate(BaseModel):
    """切换模型请求体：只带模型 id（API Key 由系统内置，不接受也不返回）。"""

    model: str | None = None


@router.get("/llm/models")
def list_models():
    """可选模型清单（后端精选，含显示名）。"""
    return LLMConfigService.list_models()


@router.get("/llm/config")
async def read_llm_config(session: AsyncSession = Depends(get_session)):
    """当前生效模型与运行状态。"""
    return await LLMConfigService(session).status()


@router.post("/llm/config")
async def write_llm_config(
    payload: ModelUpdate,
    session: AsyncSession = Depends(get_session),
):
    """切换模型：保存到配置表并即时生效。"""
    try:
        return await LLMConfigService(session).set_current_model(payload.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
