"""向量化封装（把文字转成向量）。

"向量"可以理解成用一串数字来表示一段文字的意思，文字意思越接近，数字越接近。
文案话术库要靠它做"语义检索"：找到历史上意思相近的文案当作参考。

这个文件封装了调用硅基流动向量接口的逻辑，设计原则是：任何失败都静默返回空，
绝不让"转向量失败"拖垮主流程。
"""

from __future__ import annotations

import asyncio
import logging
import time

from langchain_openai import OpenAIEmbeddings

from .settings import settings

logger = logging.getLogger("embedding")


class SiliconFlowEmbeddings:
    """向量接口封装。

    采用懒加载：第一次真正用到时才创建连接；没配置密钥就直接不可用。
    """

    def __init__(self) -> None:
        self._embeddings: OpenAIEmbeddings | None = None

    @property
    def configured(self) -> bool:
        """是否配置了密钥；没配置则调用方应静默跳过。"""
        return bool(settings.siliconflow_api_key)

    def _get(self) -> OpenAIEmbeddings:
        """懒加载：首次使用时才创建向量连接。"""
        if self._embeddings is None:
            self._embeddings = OpenAIEmbeddings(
                model=settings.siliconflow_embedding_model,
                api_key=settings.siliconflow_api_key,
                base_url=settings.siliconflow_base_url,
                request_timeout=settings.embedding_timeout,
                # 该平台接口只接受原始文本，开启长度检查反而会报错，所以关掉
                check_embedding_ctx_length=False,
            )
            logger.info("初始化 embedding 客户端 model=%s", settings.siliconflow_embedding_model)
        return self._embeddings

    async def embed_query(self, text: str) -> list[float] | None:
        """把一条文本转成向量；失败返回 None。"""
        if not self.configured or not (text or "").strip():
            return None
        started = time.time()
        try:
            # 向量接口是阻塞的，放到线程里跑，避免卡住整个服务
            result = await asyncio.to_thread(self._get().embed_query, text.strip())
            logger.info("embed_query 成功 len=%s 耗时=%.2fs", len(result), time.time() - started)
            return list(result)
        except Exception as exc:
            logger.warning("embed_query 失败 耗时=%.2fs：%s", time.time() - started, exc)
            return None

    async def embed_documents(self, texts: list[str]) -> list[list[float]] | None:
        """把一批文本转成向量；失败返回 None。"""
        if not self.configured:
            return None
        cleaned = [(t or "").strip() for t in texts]
        if not cleaned:
            return None
        started = time.time()
        try:
            result = await asyncio.to_thread(self._get().embed_documents, cleaned)
            logger.info("embed_documents 成功 条数=%s 耗时=%.2fs", len(result), time.time() - started)
            return [list(v) for v in result]
        except Exception as exc:
            logger.warning("embed_documents 失败 条数=%s 耗时=%.2fs：%s", len(cleaned), time.time() - started, exc)
            return None


# 全局唯一实例，全项目共用（懒加载，不主动创建连接）
embeddings = SiliconFlowEmbeddings()
