"""数据库初始化。

程序启动时会先执行这里，保证数据库"准备好"：
1. 检查数据库是否存在，不存在就自动创建（业务库和状态库两个）；
2. 检查表是否建好，没有就执行迁移自动建表/更新表。

这样即使在全新电脑上运行，启动后也能直接使用。
"""

from __future__ import annotations

from pathlib import Path

import pymysql

from ..core.settings import settings


def _ensure_database(database: str) -> None:
    """确保指定的数据库存在，没有就创建（用友好的字符集）。"""
    connection = pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        charset="utf8mb4",
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        connection.commit()
    finally:
        connection.close()


def init_database() -> None:
    """同时确保业务库和状态库存在。"""
    _ensure_database(settings.mysql_database)
    _ensure_database(settings.checkpoint_database)


def upgrade_database() -> None:
    """执行数据库迁移（自动建表/更新表）。"""
    init_database()
    from alembic import command
    from alembic.config import Config

    config = Config(str(Path(__file__).resolve().parent.parent.parent / "alembic.ini"))
    command.upgrade(config, "head")
