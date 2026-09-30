"""大模型连接管理。

项目要做情感分析、生成应对方案等，都需要调用外面的大模型接口（硅基流动）。
这个文件负责管理与大模型的连接：判断有没有配置密钥、按需创建连接、支持运行时切换模型。

它的核心思想是"复用"：同一个用途的连接只创建一次并缓存起来，
避免每次请求都重新建立连接、浪费时间和资源。
"""

from __future__ import annotations

import logging

from langchain_openai import ChatOpenAI

from .settings import settings

logger = logging.getLogger("llm")


class LLMGateway:
    """大模型连接管理器。

    内部用一个字典缓存已创建的连接，key 是（用途、模型、温度）的组合。
    切换模型后，key 会变化，旧连接自动作废、下次按新模型重建。
    """

    def __init__(self) -> None:
        # 缓存已创建的连接：key 是 (用途, 模型, 温度)，value 是连接对象
        self._models: dict[tuple, ChatOpenAI] = {}
        # 用户最近一次在设置页选择的模型；None 表示用 .env 里的默认模型
        self._active_model: str | None = None

    @property
    def active_model(self) -> str:
        """返回当前生效的模型名。"""
        return self._active_model or settings.siliconflow_default_model

    def set_active_model(self, model: str | None) -> None:
        """切换当前模型，并清空已缓存的连接（下次按新模型重建）。"""
        logger.info("切换 LLM 模型：%s -> %s", self.active_model, model)
        self._active_model = model
        self._models.clear()

    @property
    def configured(self) -> bool:
        """判断是否配置了密钥；没配置就只能用本地规则，不能调大模型。"""
        return bool(settings.siliconflow_api_key)

    def chat_model(self, logical_key: str = "default", temperature: float = 0) -> ChatOpenAI:
        """获取一个大模型连接，没有则新建并缓存。

        logical_key 表示用途（如"情感分析"）；temperature 控制回答的随意程度，
        0 最严谨，越大越有创意。
        """
        cache_key = (logical_key, self.active_model, temperature)
        if cache_key not in self._models:
            logger.info(
                "创建 LLM 会话 logical_key=%s model=%s temperature=%s",
                logical_key, self.active_model, temperature,
            )
            self._models[cache_key] = ChatOpenAI(
                model=self.active_model,
                api_key=settings.siliconflow_api_key,
                base_url=settings.siliconflow_base_url,
                timeout=settings.llm_timeout,
                temperature=temperature,
            )
        return self._models[cache_key]


# 全局唯一的管理器，整个项目共用
llm_gateway = LLMGateway()
