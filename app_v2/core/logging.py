"""日志初始化。

日志就是程序运行时打印的文字记录，方便看程序做了什么、出了什么问题。
这个文件在启动时做一次性初始化：让日志同时输出到控制台和文件里，
文件按大小自动轮转，避免单个日志文件无限增大。
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 控制台日志：带时间、等级、模块名和内容
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# 文件日志：写入 code/logs/app.log，单文件最大 5MB，超过后轮转保留 3 份旧档
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
try:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    _file_handler = RotatingFileHandler(
        _LOG_DIR / "app.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    _file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    logging.getLogger().addHandler(_file_handler)
except OSError:
    # 目录/文件无法创建时不阻塞启动，仅保留控制台日志
    pass
