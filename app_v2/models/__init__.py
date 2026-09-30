"""
models 数据模型包。

数据模型可以理解成"数据库表格的说明书"：
每个类对应数据库里的一张表，
方便代码里用对象的方式来读写数据。
"""
from .entities import (
    Alert,
    Analysis,
    Brand,
    Comment,
    Content,
    IssueTag,
    Keyword,
    ProductReport,
    ResponsePlan,
    SystemConfig,
)

__all__ = [
    "Alert",
    "Analysis",
    "Brand",
    "Comment",
    "Content",
    "IssueTag",
    "Keyword",
    "ProductReport",
    "ResponsePlan",
    "SystemConfig",
]