"""品牌表数据读写。

系统目前按"单品牌"运行，所以只需要一个默认品牌。这个文件负责找到默认品牌，
没有就自动创建一个。写入任何业务数据前，都要先确定属于哪个品牌。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Brand


class BrandRepository:
    """品牌表的数据库操作集合。"""

    async def get_default(self, session: AsyncSession) -> Brand:
        """获取默认品牌，没有则自动创建一个。"""
        result = await session.execute(select(Brand).where(Brand.is_default.is_(True)).limit(1))
        brand = result.scalar_one_or_none()
        if brand:
            return brand
        brand = Brand(name="默认品牌", platform="xiaohongshu", is_default=True)
        session.add(brand)
        await session.flush()
        return brand
