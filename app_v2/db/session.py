"""数据库会话管理。

程序每次操作数据库都需要一个"会话"（可以理解成一次与数据库对话的通道）：
在通道里查数据、改数据，用完提交保存，出错就回滚撤销。

这个文件负责创建连接池，并提供一个统一的获取会话函数给接口使用。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..core.settings import settings

# 创建异步数据库引擎（连接池：连接的"蓄水池"，用完放回，避免反复新建）
engine = create_async_engine(
    settings.async_database_url,
    echo=settings.debug,      # 调试模式下打印 SQL，方便排查
    pool_pre_ping=True,       # 取连接前先测试是否还活着
    pool_recycle=1800,        # 连接超过 30 分钟自动换新
    pool_size=10,             # 常规连接数
    max_overflow=10,          # 突发时最多再扩 10 个
)

# 会话工厂：按需生成一个新的会话对象
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """给接口层提供数据库会话。

    用法：接口函数通过参数注入拿到会话；请求正常结束自动提交，
    中途出错自动回滚并原样抛出异常。
    """
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
