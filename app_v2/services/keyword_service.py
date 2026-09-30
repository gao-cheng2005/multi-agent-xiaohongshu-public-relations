"""关键词业务。

给接口提供关键词的增删查，以及"记录上次触发采集时间"的能力。
真正的数据库读写细节在 KeywordRepository 里，这里只做业务衔接。
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.timeutil import utcnow
from ..repositories.base import to_dict
from ..repositories.brand_repository import BrandRepository
from ..repositories.keyword_repository import KeywordRepository


class KeywordService:
    """关键词业务服务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = KeywordRepository()
        self.brands = BrandRepository()

    async def list(self) -> list[dict]:
        """获取全部关键词，时间转成北京时间展示。"""
        from ..core.timeutil import format_dt_utc

        rows = await self.repo.list(self.session)
        items = []
        for row in rows:
            item = to_dict(row)
            # 库里存的是 UTC，转成北京时间，避免前端差 8 小时
            item["last_triggered_at"] = format_dt_utc(row.last_triggered_at)
            items.append(item)
        return items

    async def create(self, keyword: str, platform: str = "xiaohongshu") -> dict:
        """新增一个关键词（已存在则返回旧记录），返回该记录。"""
        brand = await self.brands.get_default(self.session)
        row = await self.repo.create(self.session, brand.id, keyword, platform)
        return to_dict(row)

    async def delete(self, keyword_id: uuid.UUID) -> None:
        """按编号删除一个关键词。"""
        await self.repo.delete(self.session, keyword_id)

    async def delete_all(self) -> int:
        """清空全部关键词，返回删除数量。"""
        return await self.repo.delete_all(self.session)

    async def mark_triggered(self, keyword: str) -> None:
        """记录某关键词刚刚触发过采集。"""
        await self.repo.mark_triggered(self.session, keyword, utcnow())
