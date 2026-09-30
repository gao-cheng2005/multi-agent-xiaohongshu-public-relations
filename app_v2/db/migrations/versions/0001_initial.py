"""
db/migrations/versions/0001_initial 第一个迁移版本。

迁移（migration）可以理解成"数据库版本的升级记录"：
- 第一次运行项目时，通过这个版本把数据库的表全部创建出来；
- 以后表结构改了，会再追加新的版本文件来升级。

本文件是初始版本：直接用代码里定义的表模型，一次性创建全部表。
"""
"""initial MVC schema

Revision ID: 0001
Revises:
Create Date: 2026-09-18
"""

from alembic import op

from app_v2.db.base import Base
from app_v2 import models  # noqa: F401

# 版本编号：0001 表示这是第一个版本
revision = "0001"
# 没有上一个版本（这是最初的版本）
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """向上升级：创建数据库里的所有表。

    因为表结构已经在代码模型里定义好了，这里只需要
    让 SQLAlchemy 按照模型定义把所有表创建出来即可。
    """
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    """回退版本：删除所有表。

    当需要把数据库恢复到升级前的状态时调用（一般不会用到）。
    """
    Base.metadata.drop_all(bind=op.get_bind())