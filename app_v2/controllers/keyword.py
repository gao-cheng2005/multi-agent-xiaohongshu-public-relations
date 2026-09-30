"""关键词接口。

前端"关键词管理"页面调用的接口：查看关键词列表、新增关键词、清空、删除。
接口层只接收请求和返回结果，具体逻辑在 KeywordService 里。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..models.schemas import KeywordCreate
from ..services.keyword_service import KeywordService

router = APIRouter()


@router.get("/keywords")
async def get_keywords(session: AsyncSession = Depends(get_session)):
    """获取全部关键词列表。"""
    return await KeywordService(session).list()


@router.post("/keywords")
async def create_keyword(payload: KeywordCreate, session: AsyncSession = Depends(get_session)):
    """新增一个关键词。"""
    return await KeywordService(session).create(payload.keyword, payload.platform)


@router.post("/keywords/clear")
async def clear_keywords(session: AsyncSession = Depends(get_session)):
    """清空全部关键词。"""
    count = await KeywordService(session).delete_all()
    return {"ok": True, "count": count}


@router.delete("/keywords/{keyword_id}")
async def remove_keyword(keyword_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    """按编号删除一个关键词。"""
    await KeywordService(session).delete(keyword_id)
    return {"ok": True}
