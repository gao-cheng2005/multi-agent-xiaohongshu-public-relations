"""情感与风险分析。

判断一段内容（笔记 + 评论）的情感倾向和风险等级。有两种方式：
1. 规则方式：用预设的词库数正面/负面/敏感词，不花钱、速度快；
2. 大模型方式：交给大模型理解语义，更聪明。

根据配置自动选择：auto=有密钥用大模型否则用规则；rule=强制规则；llm=强制大模型。
"""

from __future__ import annotations

# 正面词库：出现这些词通常表示好感
POSITIVE_WORDS = ["好用", "喜欢", "回购", "推荐", "惊艳", "温和", "不错", "满意", "种草", "值得"]
# 负面词库：出现这些词通常表示不满
NEGATIVE_WORDS = [
    "不好", "难用", "避雷", "差评", "过敏", "烂脸", "假货",
    "退款", "投诉", "踩雷", "垃圾", "失望", "油腻", "刺痛",
]
# 敏感词库：涉及这些词风险会升高（投诉、过敏、假货等）
SENSITIVE_WORDS = ["退款", "投诉", "过敏", "烂脸", "假货", "避雷", "维权", "监管"]


def _normalize_sentiment(value: str | None) -> str:
    """把大模型返回的情感值统一规整成"正面/中性/负面"。"""
    text = str(value or "").strip().lower()
    if text in ("正面", "positive", "neutral-positive", "中性偏正面"):
        return "正面"
    if text in ("负面", "negative", "neutral-negative", "中性偏负面"):
        return "负面"
    return "中性"


def _normalize_risk(value: str | None) -> str:
    """把大模型返回的风险等级统一规整成"低/中/高"。"""
    text = str(value or "").strip().lower()
    if text in ("高", "high", "critical"):
        return "高"
    if text in ("中", "medium", "moderate"):
        return "中"
    return "低"


def rule_analyze(text: str, comments: list[str] | None = None) -> dict:
    """用规则词库做情感分析（不调用大模型）。

    思路：统计正文和评论里命中正面词、负面词、敏感词的次数，
    按多少比较得出情感，再用是否有敏感词判断风险等级。
    """
    from ...core.cleaning import is_negated

    positive = 0
    negative = 0
    # 第一步：分析正文，统计正/负/敏感词命中数（注意否定语境）
    for word in POSITIVE_WORDS:
        if word in text:
            if is_negated(text, word):  # 被否定（如"不好用"）算负面
                negative += 1
            else:
                positive += 1
    for word in NEGATIVE_WORDS:
        if word in text and not is_negated(text, word):
            negative += 1
    sensitive = [w for w in SENSITIVE_WORDS if w in text and not is_negated(text, w)]

    # 第二步：分析评论，同样统计（评论更能反映真实口碑）
    comment_text = " ".join(comments or [])
    for word in NEGATIVE_WORDS:
        if word in comment_text:
            if is_negated(comment_text, word):
                positive += 1
            else:
                negative += 1
    for word in POSITIVE_WORDS:
        if word in comment_text and not is_negated(comment_text, word):
            positive += 1

    # 第三步：按命中多少判断情感
    if negative > positive:
        sentiment, score = "负面", -0.6
    elif negative > 0:
        sentiment, score = "中性", -0.2
    elif positive > 0:
        sentiment, score = "正面", 0.6
    else:
        sentiment, score = "中性", 0.0

    # 第四步：计算可信度（正负差异越明显越可信）
    total = positive + negative
    confidence = round(0.5 + (abs(positive - negative) / (total + 1)) * 0.4, 2) if total else 0.5
    # 第五步：定风险等级：有敏感词=高；负面=中；否则低
    risk_level = "高" if sensitive else ("中" if sentiment == "负面" else "低")
    summary = (
        f"规则词库分析：正文与评论共命中正面词 {positive} 个、负面词 {negative} 个"
        + (f"，命中敏感词：{', '.join(sensitive)}" if sensitive else "")
    )
    return {
        "sentiment": sentiment,
        "confidence": confidence,
        "topics": [],
        "keywords": [w for w in POSITIVE_WORDS + NEGATIVE_WORDS if w in text],
        "risk_level": risk_level,
        "score": score,
        "summary": summary,
        "model": "rule",
    }


def _configured() -> bool:
    """判断是否配置了大模型密钥。"""
    from ...core.llm import llm_gateway
    return llm_gateway.configured


def rule_sentiment(text: str) -> str:
    """规则兜底：只返回情感倾向。"""
    return rule_analyze(text)["sentiment"]


def rule_risk(text: str, comments: list[str] | None = None) -> dict:
    """规则兜底：基于敏感词/情感给出风险等级、分数与是否需尽快干预。"""
    analysis = rule_analyze(text, comments)
    sensitive = analysis["risk_level"] == "高"
    urgent = analysis["sentiment"] == "负面"
    return {
        "risk_level": analysis["risk_level"],
        "reason": analysis["summary"],
        "harm_score": 8 if sensitive else (5 if analysis["sentiment"] == "负面" else 2),
        "spread_score": 5,
        "urgent": urgent,
        "model": "rule",
    }


async def analyze_sentiment(note: dict) -> dict:
    """① 情感分析（大模型优先，失败走规则）。

    输入是笔记字典（用 title/body），输出统一格式：{"sentiment", "confidence", "model"}。
    """
    from ...core.settings import settings
    from ...core.llm import llm_gateway

    text = f"{note.get('title', '')} {note.get('body', '')}"
    # 强制大模型 或 自动模式且已配置密钥：尝试用大模型
    if settings.sentiment_mode == "llm" or _configured():
        try:
            from .factory import run_note_sentiment_agent

            data = (
                await run_note_sentiment_agent(
                    f"笔记标题：{note.get('title', '')}\n笔记正文：{note.get('body', '')}"
                )
            ).model_dump()
            return {
                "sentiment": data.get("sentiment", "中性"),
                "confidence": data.get("confidence", 0.5),
                "model": llm_gateway.active_model,
            }
        except Exception:
            if settings.sentiment_mode == "llm":  # 强制大模型模式：失败必须报错
                raise
    # 规则兜底
    return {"sentiment": rule_sentiment(text), "confidence": 0.5, "model": "rule"}


async def analyze_risk(note: dict, comments: list[dict] | None = None) -> dict:
    """② 风险评估（大模型优先，失败走规则）。

    输入：笔记字典（含互动数字）+ 评论列表；
    输出：{"risk_level", "summary", "score", "harm_score", "spread_score", "urgent", "model"}。
    """
    from ...core.settings import settings
    from ...core.llm import llm_gateway

    text = f"{note.get('title', '')} {note.get('body', '')}"
    comment_texts = [c.get("content", "") for c in (comments or [])]
    if settings.sentiment_mode == "llm" or _configured():
        try:
            from ...models.schemas import RiskResult
            from .factory import run_risk_agent

            comment_lines = "\n".join(f"- {t[:120]}" for t in comment_texts[:30]) or "（无评论）"
            payload = (
                f"笔记正文：{text[:2000]}\n"
                f"互动：点赞{note.get('like_count', 0)} 收藏{note.get('collect_count', 0)} "
                f"转发{note.get('share_count', 0)} 评论数{note.get('comment_count', 0)}\n"
                f"发布时间：{note.get('published_at') or '未知'}\n"
                f"评论区：\n{comment_lines}"
            )
            result: RiskResult = await run_risk_agent(payload)
            return {
                "risk_level": result.risk_level,
                "summary": result.reason,
                "score": result.harm_score,
                "harm_score": result.harm_score,
                "spread_score": result.spread_score,
                "urgent": result.urgent,
                "model": llm_gateway.active_model,
            }
        except Exception:
            if settings.sentiment_mode == "llm":  # 强制大模型模式：失败必须报错
                raise
    # 规则兜底
    return rule_risk(text, comment_texts)
