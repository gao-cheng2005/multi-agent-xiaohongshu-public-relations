"""系统配置接口。

前端"设置"页面调用的接口：读取配置项、修改配置项。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..models.schemas import ConfigUpdate
from ..services.system_config_service import SystemConfigService

router = APIRouter()


@router.get("/config")
async def read_config(key: str | None = Query(default=None), session: AsyncSession = Depends(get_session)):
    """读取配置：传了 key 只看那一项，不传看全部。"""
    return await SystemConfigService(session).get(key)


@router.post("/config")
async def write_config(payload: ConfigUpdate, session: AsyncSession = Depends(get_session)):
    """新增或修改一个配置项。"""
    return await SystemConfigService(session).upsert(payload.key, payload.value)
