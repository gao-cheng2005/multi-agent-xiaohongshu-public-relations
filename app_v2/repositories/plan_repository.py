"""应对方案表数据读写。

"应对方案"是一篇笔记的处置建议（含渠道、文案、状态）。一篇笔记最多一份方案，
重新生成会覆盖旧内容。这个文件负责方案表的所有数据库操作。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ResponsePlan


class ResponsePlanRepository:
    """应对方案表的数据库操作集合。"""

    async def get_by_content_id(self, session: AsyncSession, content_id: str) -> ResponsePlan | None:
        """按笔记编号查找方案（一篇笔记最多一份）。"""
        result = await session.execute(
            select(ResponsePlan).where(ResponsePlan.content_id == content_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self, session: AsyncSession, brand_id: uuid.UUID, content_id: str, trigger: str, plan: dict
    ) -> ResponsePlan:
        """新建或更新某笔记的方案。

        有旧方案就更新内容并把状态重置为"待决策"，没有就新建。
        """
        instance = await self.get_by_content_id(session, content_id)
        if instance is None:
            instance = ResponsePlan(
                brand_id=brand_id, content_id=content_id, trigger=trigger, status="pending", **plan
            )
            session.add(instance)
        else:
            instance.trigger = trigger
            instance.status = "pending"
            instance.decided_at = None
            instance.decided_by = ""
            for key, value in plan.items():
                setattr(instance, key, value)
        await session.flush()
        return instance

    async def get(self, session: AsyncSession, plan_id: uuid.UUID) -> ResponsePlan | None:
        """按编号查找一份方案。"""
        return await session.get(ResponsePlan, plan_id)

    async def mark_status(self, session: AsyncSession, plan_id: uuid.UUID, status: str) -> ResponsePlan | None:
        """更新方案的流程状态（pending/processing/done/skipped/failed）。"""
        row = await self.get(session, plan_id)
        if row:
            row.status = status
            await session.flush()
        return row

    async def list(self, session: AsyncSession, content_id: str | None = None):
        """列出方案；可传笔记编号只列某一篇，新的排前面。"""
        statement = select(ResponsePlan)
        if content_id:
            statement = statement.where(ResponsePlan.content_id == content_id)
        result = await session.execute(statement.order_by(ResponsePlan.created_at.desc()))
        return list(result.scalars().all())
