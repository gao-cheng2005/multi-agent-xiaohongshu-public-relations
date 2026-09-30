"""关键词表数据读写。

"关键词"是运营人员配置的监控词，采集时按这些词去搜笔记。这个文件负责关键词表的
数据库操作：列出、按内容查、新建（已存在则返回旧的）、删除、记录触发时间。
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Keyword


class KeywordRepository:
    """关键词表的数据库操作集合。"""

    async def list(self, session: AsyncSession) -> list[Keyword]:
        """列出全部关键词，新建的排在前面。"""
        result = await session.execute(select(Keyword).order_by(Keyword.created_at.desc()))
        return list(result.scalars().all())

    async def get_by_keyword(self, session: AsyncSession, keyword: str) -> Keyword | None:
        """按关键词内容查找记录。"""
        result = await session.execute(select(Keyword).where(Keyword.keyword == keyword))
        return result.scalar_one_or_none()

    async def create(
        self, session: AsyncSession, brand_id: uuid.UUID, keyword: str, platform: str = "xiaohongshu"
    ) -> Keyword:
        """新增关键词；已存在则直接返回旧记录。"""
        existing = await self.get_by_keyword(session, keyword)
        if existing:
            return existing
        instance = Keyword(brand_id=brand_id, keyword=keyword, platform=platform, enabled=True)
        session.add(instance)
        await session.flush()
        return instance

    async def delete(self, session: AsyncSession, keyword_id: uuid.UUID) -> None:
        """按编号删除一个关键词。"""
        await session.execute(delete(Keyword).where(Keyword.id == keyword_id))

    async def delete_all(self, session: AsyncSession) -> int:
        """清空全部关键词，返回删除数量。"""
        result = await session.execute(delete(Keyword))
        return result.rowcount or 0

    async def mark_triggered(self, session: AsyncSession, keyword: str, timestamp) -> None:
        """记录某关键词上次触发采集的时间。"""
        result = await session.execute(select(Keyword).where(Keyword.keyword == keyword))
        instance = result.scalar_one_or_none()
        if instance:
            instance.last_triggered_at = timestamp
