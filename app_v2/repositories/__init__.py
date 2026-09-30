"""
repositories 数据访问层（对数据库的读写操作都放在这里）。

为什么要有这一层？
- 业务逻辑层（services）负责"想做什么"；
- 这里负责"具体怎么从数据库取出/写入数据"。
这样把两件事分开，代码会更清晰、更好维护。
"""
from .alert_repository import AlertRepository
from .analysis_repository import AnalysisRepository
from .brand_repository import BrandRepository
from .content_repository import ContentRepository
from .keyword_repository import KeywordRepository
from .plan_repository import ResponsePlanRepository
from .system_config_repository import SystemConfigRepository

__all__ = [
    "AlertRepository",
    "AnalysisRepository",
    "BrandRepository",
    "ContentRepository",
    "KeywordRepository",
    "ResponsePlanRepository",
    "SystemConfigRepository",
]