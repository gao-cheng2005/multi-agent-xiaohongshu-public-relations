"""系统配置业务。

给"设置"页面提供通用配置的读取和修改能力。
配置是简单的 key-value 结构，具体读写细节在 SystemConfigRepository 里。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.base import to_dict
from ..repositories.brand_repository import BrandRepository
from ..repositories.system_config_repository import SystemConfigRepository


class SystemConfigService:
    """系统配置业务服务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = SystemConfigRepository()
        self.brands = BrandRepository()

    async def list(self) -> list[dict]:
        """列出全部配置项。"""
        rows = await self.repo.list(self.session)
        return [to_dict(row) for row in rows]

    async def get(self, key: str) -> list[dict]:
        """读取配置：传了 key 只看那一项，不传看全部。"""
        if key:
            row = await self.repo.get(self.session, key)
            return [to_dict(row)] if row else []
        return await self.list()

    async def upsert(self, key: str, value: str) -> dict:
        """新增或修改一个配置项。"""
        brand = await self.brands.get_default(self.session)
        row = await self.repo.upsert(self.session, brand.id, key, value)
        return to_dict(row)
