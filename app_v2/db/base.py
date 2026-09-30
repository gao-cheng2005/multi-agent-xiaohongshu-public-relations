"""数据模型的基础部分。

所有数据库表都用这里定义的类作为"地基"：
- Base：普通表的基类，告诉 SQLAlchemy 哪些类对应数据库表；
- TimestampMixin：给表统一加上"创建时间"和"更新时间"两列。

（SQLAlchemy 是让代码用对象方式操作数据库的工具，不需要直接写很多 SQL。）
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ..core.timeutil import utcnow


class Base(DeclarativeBase):
    """所有表模型的公共基类。"""
    pass


class TimestampMixin:
    """给表加上自动的时间记录。

    加了之后，表就自动拥有 created_at（创建时间）和 updated_at（更新时间），
    并在写入/修改时自动填充。
    """

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
