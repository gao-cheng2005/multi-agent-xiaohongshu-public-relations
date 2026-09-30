"""系统配置表数据读写。

系统配置是通用的 key-value 结构，设置页用它存一些简单的选项。
这个文件负责配置表的列出、按名查、新增或更新。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import SystemConfig


class SystemConfigRepository:
    """系统配置表的数据库操作集合。"""

    async def list(self, session: AsyncSession) -> list[SystemConfig]:
        """列出全部配置项，按创建先后排列。"""
        result = await session.execute(select(SystemConfig).order_by(SystemConfig.created_at))
        return list(result.scalars().all())

    async def get(self, session: AsyncSession, key: str) -> SystemConfig | None:
        """按配置项名字查找一条配置。"""
        result = await session.execute(
            select(SystemConfig).where(SystemConfig.config_key == key)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self, session: AsyncSession, brand_id: uuid.UUID, key: str, value: str
    ) -> SystemConfig:
        """新增或更新一个配置项（有就改值，没有就新建）。"""
        instance = await self.get(session, key)
        if instance is None:
            instance = SystemConfig(brand_id=brand_id, config_key=key, config_value=value)
            session.add(instance)
        else:
            instance.config_value = value
        await session.flush()
        return instance
