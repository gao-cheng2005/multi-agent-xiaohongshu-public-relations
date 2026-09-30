"""大模型运行时配置。

设置页在这里完成两件事：查看当前生效的模型；切换模型（校验 → 存库 → 立即生效）。
注意 API Key 不在这里暴露，它固定从 .env 读取。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.llm import llm_gateway
from ..core.settings import LLM_MODELS, settings
from ..repositories.base import to_dict
from ..repositories.brand_repository import BrandRepository
from ..repositories.system_config_repository import SystemConfigRepository

LLM_MODEL_KEY = "llm_model"  # 存"用户所选模型"的配置项 key


class LLMConfigService:
    """大模型运行时配置服务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = SystemConfigRepository()
        self.brands = BrandRepository()

    @staticmethod
    def list_models() -> list[dict]:
        """返回精选模型清单（id + 显示名），供设置页下拉选择。"""
        return [{"id": mid, "name": name} for mid, name in LLM_MODELS]

    async def get_current_model(self) -> str:
        """当前生效模型：优先取用户存过的，否则用 .env 默认。"""
        row = await self.repo.get(self.session, LLM_MODEL_KEY)
        if row and row.config_value:
            return row.config_value
        return settings.siliconflow_default_model

    async def set_current_model(self, model: str | None) -> dict:
        """切换模型并立即生效。

        流程：校验是否在可用清单内 → 写入配置表 → 通知连接管理器切换并清缓存。
        """
        model = (model or "").strip() or settings.siliconflow_default_model
        allowed = {mid for mid, _ in LLM_MODELS}
        if model not in allowed:
            raise ValueError(f"模型不在可用清单内：{model}")

        brand = await self.brands.get_default(self.session)
        row = await self.repo.upsert(self.session, brand.id, LLM_MODEL_KEY, model)
        llm_gateway.set_active_model(model)

        data = to_dict(row)
        data["active_model"] = llm_gateway.active_model
        return data

    async def status(self) -> dict:
        """当前大模型运行状态（绝不返回 API Key）。"""
        return {
            "provider": "siliconflow",
            "base_url": settings.siliconflow_base_url,
            "model": await self.get_current_model(),
            "configured": llm_gateway.configured,
            "models": self.list_models(),
        }
