"""系统配置读取。

项目里所有可变的配置（数据库地址、大模型密钥、超时时间等）都写在外面的 .env 文件里，
不在代码里写死。这个文件负责在启动时把这些配置读进来，集中挂在 settings 对象上，
其他代码要用配置时，直接 import settings 再取对应字段即可。

这样做的好处是：不同环境（开发、部署）改配置时，只改 .env 文件，不用动代码。
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

# 项目根目录：app_v2 的上上级（也就是 code 目录）
BASE_DIR = Path(__file__).resolve().parent.parent.parent
# 把根目录下 .env 文件里的配置加载到环境变量里
load_dotenv(BASE_DIR / ".env")


def _env(key: str, default: str) -> str:
    """从环境变量里读一个配置值，没配置就用兜底默认值。"""
    value = os.getenv(key)
    return value if value not in (None, "") else default


def _resolve_path(raw: str, default: Path) -> Path:
    """把配置里的路径整理成完整路径：绝对路径直接用，相对路径拼到项目根目录下。"""
    path = Path(raw)
    return path if path.is_absolute() else BASE_DIR / path


class Settings:
    """项目配置的集合。

    把分散的配置集中挂在同一个对象上（例如 settings.mysql_host），
    其他代码只需要 import 这个对象，就能拿到所有想用的配置。
    """

    # ---- 应用基础信息 ----
    app_name: str = "舆情公关多 Agent 平台 V2"
    debug: bool = _env("APP_DEBUG", "false").lower() == "true"

    # ---- MySQL 业务数据库（存笔记、评论、预警等业务数据） ----
    mysql_host: str = _env("MYSQL_HOST", "127.0.0.1")
    mysql_port: int = int(_env("MYSQL_PORT", "3306"))
    mysql_user: str = _env("MYSQL_USER", "root")
    mysql_password: str = _env("MYSQL_PASSWORD", "")
    mysql_database: str = _env("MYSQL_DATABASE", "yuqing_pr")
    checkpoint_database: str = _env("CHECKPOINT_DATABASE", "yuqing_pr_langgraph")  # 存流程中间状态

    # ---- ChromaDB 向量库（存知识向量，用于相似内容检索） ----
    chroma_host: str = _env("CHROMA_HOST", "127.0.0.1")
    chroma_port: int = int(_env("CHROMA_PORT", "8001"))
    chroma_persist_dir: Path = _resolve_path(
        _env("CHROMA_PERSIST_DIR", "data/chroma"), BASE_DIR / "data" / "chroma"
    )

    # ---- 大模型（硅基流动）配置 ----
    siliconflow_api_key: str = _env("SILICONFLOW_API_KEY", "")
    siliconflow_base_url: str = _env("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
    siliconflow_default_model: str = _env("SILICONFLOW_DEFAULT_MODEL", "Qwen/Qwen2.5-7B-Instruct")
    sentiment_mode: str = _env("SENTIMENT_MODE", "auto")  # auto=有密钥用大模型否则用规则；llm=强制大模型；rule=强制规则
    llm_timeout: int = int(_env("LLM_TIMEOUT", "60"))

    # ---- RAG（检索增强生成）配置：文案话术库 ----
    siliconflow_embedding_model: str = _env("SILICONFLOW_EMBEDDING_MODEL", "BAAI/bge-large-zh-v1.5")
    embedding_timeout: int = int(_env("EMBEDDING_TIMEOUT", "5"))
    rag_enabled: bool = _env("RAG_ENABLED", "false").lower() == "true"  # 总开关
    rag_top_k: int = int(_env("RAG_TOP_K", "3"))  # 返回参考文案条数上限

    # ---- 抓取工具 OpenCLI 的命令名 ----
    opencli_bin: str = _env("OPENCLI_BIN", "opencli")

    @property
    def async_database_url(self) -> str:
        """组装程序主代码使用的异步数据库连接串（mysql+asyncmy）。"""
        password = quote_plus(self.mysql_password)
        return (
            f"mysql+asyncmy://{self.mysql_user}:{password}@"
            f"{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )

    @property
    def sync_database_url(self) -> str:
        """组装数据库迁移工具使用的同步连接串（mysql+pymysql）。"""
        password = quote_plus(self.mysql_password)
        return (
            f"mysql+pymysql://{self.mysql_user}:{password}@"
            f"{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )

    @property
    def checkpoint_url(self) -> str:
        """组装流程中间状态库的连接串。"""
        password = quote_plus(self.mysql_password)
        return (
            f"mysql://{self.mysql_user}:{password}@"
            f"{self.mysql_host}:{self.mysql_port}/{self.checkpoint_database}"
        )


# 设置页下拉可选模型清单（id, 显示名），只放经确认可用的模型
LLM_MODELS: list[tuple[str, str]] = [
    ("Qwen/Qwen2-7B-Instruct", "Qwen2-7B"),
    ("Qwen/Qwen2.5-7B-Instruct", "Qwen2.5-7B"),
    ("Qwen/Qwen2.5-72B-Instruct", "Qwen2.5-72B"),
    ("deepseek-ai/DeepSeek-V3", "DeepSeek-V3"),
    ("deepseek-ai/DeepSeek-R1", "DeepSeek-R1（推理）"),
    ("THUDM/GLM-4-9B-0414", "GLM-4-9B"),
]

# 全局唯一的配置对象，整个项目共用
settings = Settings()
