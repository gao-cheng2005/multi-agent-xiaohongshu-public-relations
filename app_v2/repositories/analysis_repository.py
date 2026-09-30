"""分析结果表数据读写。

每次对笔记做情感/风险分析后，都会把结果存到"分析"表里。这个文件负责分析表的
数据库操作：替换某篇笔记的分析、取最新分析、列全部分析。

设计上"一篇笔记只保留最新一份分析"，重新分析时先删旧的再写新的。
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Analysis


class AnalysisRepository:
    """分析表的数据库操作集合。"""

    async def replace_for_content(
        self, session: AsyncSession, brand_id: uuid.UUID, content_id: str, analysis: dict
    ) -> Analysis:
        """替换某篇笔记的分析结果（只保留最新一份）。"""
        await session.execute(delete(Analysis).where(Analysis.content_id == content_id))
        instance = Analysis(brand_id=brand_id, content_id=content_id, **analysis)
        session.add(instance)
        await session.flush()
        return instance

    async def latest_for_content(self, session: AsyncSession, content_id: str) -> Analysis | None:
        """取某篇笔记最新的一份分析结果。"""
        result = await session.execute(
            select(Analysis)
            .where(Analysis.content_id == content_id)
            .order_by(Analysis.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_latest(self, session: AsyncSession) -> list[Analysis]:
        """列出全部分析记录，新的在前。"""
        result = await session.execute(select(Analysis).order_by(Analysis.created_at.desc()))
        return list(result.scalars().all())
