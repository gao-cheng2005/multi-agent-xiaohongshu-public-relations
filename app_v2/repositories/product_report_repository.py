"""产品优化建议缓存表数据读写。

每个产品一份最新的优化建议报告，生成后缓存到这张表，页面直接读缓存展示（秒开）。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ProductReport


class ProductReportRepository:
    """产品优化建议缓存表的数据库操作集合。"""

    async def get(self, session: AsyncSession, product: str) -> ProductReport | None:
        """按产品名读取最新报告，无则返回 None。"""
        result = await session.execute(
            select(ProductReport).where(ProductReport.product == product)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self, session: AsyncSession, brand_id: uuid.UUID, product: str, report: dict
    ) -> ProductReport:
        """保存（或更新）一份产品报告。"""
        row = await self.get(session, product)
        if row is None:
            row = ProductReport(brand_id=brand_id, product=product, report=report)
            session.add(row)
        else:
            row.report = report
        await session.flush()
        return row
