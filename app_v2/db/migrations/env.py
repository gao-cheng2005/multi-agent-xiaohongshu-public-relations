"""
db/migrations/env 迁移环境配置。

alembic（数据库结构管理工具）在执行迁移时会先加载这个文件，
告诉它：
- 用哪个数据库；
- 表长什么样（从 models 里读取）；
- 用哪种方式执行（连上数据库在线执行）。
"""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app_v2.core.settings import settings
from app_v2.db.base import Base
from app_v2 import models  # noqa: F401   （导入模型，确保所有表都被记录）

# 拿到 alembic 的上下文配置
config = context.config
if config.config_file_name is not None:
    # 读取 alembic.ini 里的日志设置。
    # disable_existing_loggers=False 很关键：不要关掉 uvicorn 等其他模块的日志，
    # 否则启动后 uvicorn 的运行日志会全部消失，像"后台没输出"一样。
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# 覆盖配置里的数据库地址，统一用项目里的配置
config.set_main_option("sqlalchemy.url", settings.sync_database_url)
# 记录所有表的结构，迁移时以此为准
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：不真正连数据库，只生成要执行的 SQL 语句。"""
    # 配置连接和表结构，准备好迁移环境
    context.configure(
        url=settings.sync_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    # 开启事务并执行迁移
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：真正连上数据库执行迁移（正常启动时用这种）。"""
    # 根据配置创建数据库连接（每次用完即弃，不留连接池）
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    # 建立连接，配置迁移环境，然后执行迁移
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


# 程序启动时会自动进入对应的迁移模式（默认在线）
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()