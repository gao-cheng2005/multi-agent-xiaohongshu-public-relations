"""
repositories/base 数据转换小工具。

数据库里的记录（对象形式）在返回给前端之前，
要转成普通的字典（类似 JSON 的对象）才能传给网页。
这个文件就是做这个转换的通用工具。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import inspect


def to_dict(instance: Any) -> dict[str, Any]:
    """把一条数据库记录转换成字典。

    例如数据库里的一条评论对象，会转成一个字典，
    里面的每个字段（作者、内容、时间等）变成字典的键值对，
    方便直接序列化成 JSON 返回给前端。
    """
    # 用 SQLAlchemy 的检查工具拿到这条记录的所有字段
    mapper = inspect(instance).mapper
    # 把每个字段名和值配对，组成字典返回
    return {column.key: getattr(instance, column.key) for column in mapper.column_attrs}