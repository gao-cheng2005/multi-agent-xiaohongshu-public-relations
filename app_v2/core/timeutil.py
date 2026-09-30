"""时间处理小工具。

平台返回的时间很多不是标准格式，而是"刚刚""3小时前""07-30上海"这样的展示文字，
没法直接存进数据库。这个文件提供统一的解析和格式化函数：
存的时候用世界标准时间（UTC），展示的时候转成北京时间，解析不了的保留原文、返回空。

文件里的函数被采集、内容、统计等多个模块共同使用。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

# 常见的时间书写格式，解析时按顺序逐个尝试
_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d",
)

# 项目按中国时区展示时间（北京时间 = UTC+8，没有夏令时）
_LOCAL_TZ = timezone(timedelta(hours=8))

# 匹配小红书链接里的笔记编号（24 位十六进制）
_XHS_ID_RE = re.compile(r"/(?:search_result|discovery/item|explore|note)/([0-9a-f]{24})")


def utcnow() -> datetime:
    """获取当前的世界标准时间（UTC）。

    统一用 UTC 存储，是为了让不同电脑上记录的时间口径一致，方便日后对比和排序。
    """
    return datetime.now(timezone.utc)


def format_dt_utc(value, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """把库里存的 UTC 时间格式化成北京时间字符串。

    数据库存的是 UTC，但直接给前端会让浏览器按本地时区解析而差 8 小时，
    所以这里统一加 8 小时再转成字符串。
    """
    if not value:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(_LOCAL_TZ).strftime(fmt)


def format_dt(value, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """把本来就是本地日期的时间字段直接格式化成字符串，不再加时区偏移。"""
    if not value:
        return ""
    return value.strftime(fmt)


def published_at_from_xhs_url(url: str) -> str:
    """从小红书笔记链接推导近似发布日期。

    小红书笔记 ID 的前 8 位十六进制其实是笔记创建时刻的时间戳，
    用它换算成北京时间日期，作为发布时间展示；拿不到编号时返回空。
    """
    if not url:
        return ""
    match = _XHS_ID_RE.search(url)
    if not match:
        return ""
    try:
        ts = int(match.group(1)[:8], 16)
    except ValueError:
        return ""
    # 时间戳明显不在合理范围内就放弃
    if ts < 1_000_000_000 or ts > 4_000_000_000:
        return ""
    return datetime.fromtimestamp(ts, _LOCAL_TZ).strftime("%Y-%m-%d")


def parse_datetime(value) -> datetime | None:
    """把各种格式的时间文字转成标准时间对象，转不了就返回空。

    能识别标准日期字符串就转换；像"刚刚""3小时前"这类展示文字解析不了，
    直接返回空，原文会保留在原始数据里，不会丢信息。
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    # 按预先定义好的格式依次尝试
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    # 最后尝试 ISO 国际标准写法
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
