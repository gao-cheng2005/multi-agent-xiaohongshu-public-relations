"""文本清洗与去重小工具。

采集回来的原始数据往往比较"脏"：有多余空格、带单位的大数字（如"1.2万"）、
重复的链接等。这个文件负责把这些数据处理成干净、统一的样子，方便存数据库和做分析。

文件里的每个函数都只做一件简单的事，彼此独立，可以被项目各处重复使用。
"""

from __future__ import annotations

import hashlib
import re

# 提前编译好常用的正则表达式，用的时候更快
_WS_RE = re.compile(r"\s+")  # 匹配连续空格/换行
_CN_NUM_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(万|千|w|W|k|K)")  # 匹配"数字+单位"

# 否定词表：用来判断一句话里是不是在说"不……"
# 例如"不用避雷"其实是在说"不必避开"，而不是负面意思
_NEGATION_PREFIXES = (
    "不用", "无需", "不必", "不要", "不会", "没有", "并非", "从未", "不过",
    "别", "不", "没", "无", "莫", "勿",
)


def normalize_url(url: str) -> str:
    """把链接整理成统一格式。

    只保留链接主体，去掉问号后面的参数（例如追踪用的签名 token），
    再去掉末尾多余的斜杠。这样同一个页面即使参数不同，也算同一条链接。
    """
    return (url or "").strip().split("?")[0].rstrip("/")


def dedup_hash(url: str) -> str:
    """根据链接计算一个固定长度的"指纹"。

    用整理后的链接算出哈希值（一串固定长度的编号），内容一样的链接算出的编号就一样，
    之后判断重复时直接比较这个指纹即可。
    """
    return hashlib.sha1(normalize_url(url).encode("utf-8")).hexdigest()


def clean_text(text: str) -> str:
    """把文本清理干净。

    去掉首尾空格，再把中间连续的多个空格/换行缩成一个，
    让文字整齐统一，方便存库和分析。
    """
    return _WS_RE.sub(" ", (text or "").strip())


def is_negated(text: str, word: str, window: int = 6) -> bool:
    """判断某个词在句子里是不是被否定词修饰了。

    例如在"不用避雷"里，"避雷"前面有"不用"，就认为它被否定。
    window 表示往前看多少个字的距离内找否定词。
    """
    text = text or ""
    start = 0
    # 在一段文字里循环搜索这个词出现的每个位置
    while True:
        idx = text.find(word, start)
        if idx == -1:
            return False
        # 取出这个词前面一小段文字，看结尾有没有否定词
        prefix = text[max(0, idx - window):idx]
        if any(prefix.endswith(neg) for neg in _NEGATION_PREFIXES):
            return True
        # 继续从这个词后面接着找，防止一个词出现多次
        start = idx + len(word)


def parse_count(value) -> int:
    """把各种写法的人数/点赞数转成真正的整数。

    平台上可能显示"1.2万""3千""487"甚至带逗号的形式，
    这个函数把它们统一换算成整数，方便比较和统计。
    """
    # 空值当作 0 处理
    if value is None:
        return 0
    # 本来就是数字的直接转整数
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return 0
    # 先看是不是"数字+万/千"这种写法，按单位换算
    match = _CN_NUM_RE.search(text)
    if match:
        number = float(match.group(1))
        unit = match.group(2).lower()
        return int(number * (10000 if unit in ("万", "w") else 1000))
    # 普通写法：把文字里的数字挑出来拼成整数（如"487 个"→487）
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0
