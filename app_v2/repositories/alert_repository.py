"""预警表数据读写。

"预警"是系统发现负面/高风险内容后生成的待处理记录。这个文件负责预警表的所有
数据库操作：替换某篇笔记的预警、按笔记查预警、列全部预警、批量标记已处理。

它只负责读写数据库，不包含业务规则（业务规则在 alert_service 里）。
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Alert


class AlertRepository:
    """预警表的数据库操作集合。"""

    async def replace_for_content(
        self, session: AsyncSession, brand_id: uuid.UUID, content_id: str, alerts: list[dict]
    ) -> list[Alert]:
        """把某篇笔记的预警整体替换成最新一批。

        思路：先删掉旧预警，再写入新的，保证每次分析后预警都是最新的。
        """
        await session.execute(delete(Alert).where(Alert.content_id == content_id))
        instances = [Alert(brand_id=brand_id, content_id=content_id, **item) for item in alerts]
        session.add_all(instances)
        await session.flush()
        return instances

    async def list_by_content(self, session: AsyncSession, content_id: str) -> list[Alert]:
        """查询某条笔记（或评论）的所有预警。"""
        result = await session.execute(select(Alert).where(Alert.content_id == content_id))
        return list(result.scalars().all())

    async def list_all(self, session: AsyncSession) -> list[Alert]:
        """查询全部预警，按创建时间从新到旧排列。"""
        result = await session.execute(select(Alert).order_by(Alert.created_at.desc()))
        return list(result.scalars().all())

    async def handle_by_ids(
        self, session: AsyncSession, alert_ids: list[uuid.UUID], status: str, timestamp
    ) -> int:
        """把一批预警标记为指定状态，返回实际处理条数。"""
        count = 0
        for alert_id in alert_ids:
            instance = await session.get(Alert, alert_id)
            if instance:
                instance.status = status
                instance.handled_at = timestamp
                count += 1
        await session.flush()
        return count
