"""预警接口。

前端"预警"页面调用的接口都在这里：查看预警列表、把一条预警标记为已处理、
把某笔记相关的全部预警标记为已处理。

接口层只负责接收请求、校验参数、调用服务层并返回结果，不写业务逻辑。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..services.alert_service import AlertService

router = APIRouter()


@router.get("/alerts")
async def get_alerts(status: str | None = Query(default=None), session: AsyncSession = Depends(get_session)):
    """获取预警列表，可传 status（open/handled）过滤。"""
    return await AlertService(session).list_alerts(status)


@router.post("/alerts/{alert_id}/handle")
async def handle_alert(alert_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    """把某一条预警标记为已处理。"""
    await AlertService(session).handle(alert_id)
    return {"ok": True}


@router.post("/alerts/note/{note_id}/handle")
async def handle_note_alerts(note_id: str, session: AsyncSession = Depends(get_session)):
    """把某笔记相关的全部预警标记为已处理，返回处理条数。"""
    count = await AlertService(session).handle_note(note_id)
    return {"ok": True, "count": count}
