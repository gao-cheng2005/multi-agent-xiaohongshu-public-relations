"""方案流程里的纯判定逻辑。

这些函数只做"判断"，不调用大模型、不碰数据库，因此非常容易测试，
也是整个流程稳定性的地基：该不该生成方案、打分是否达标、处理中是否卡住超时。
"""

from __future__ import annotations

from datetime import datetime, timezone


def should_generate(sentiment: str, risk_level: str) -> bool:
    """判断一篇笔记是否需要生成应对方案。

    设计定稿：情感为正面/中性 且 风险为低 → 无需处理（跳过生成）；
    其余情况（含刚发布的中风险负面等）都需要生成。
    """
    return not (sentiment in ("正面", "中性") and risk_level == "低")


def score_passed(total: float, dimension_scores: dict) -> bool:
    """判断文案打分是否达标：总分 ≥ 8 且无任何单项 ≤ 5。"""
    if total < 8:
        return False
    return all(value > 5 for value in (dimension_scores or {}).values())


def is_stale_processing(updated_at, now: datetime | None = None, timeout_seconds: int = 600) -> bool:
    """判断一条"处理中"记录是否已卡住超时，需要重置为失败。

    场景：进程重启后，正在跑的任务中断，状态会永远停在 processing，
    靠这个函数识别出这些卡住的记录。
    """
    if not updated_at:
        return False
    now = now or datetime.now(timezone.utc)
    # 兼容数据库返回的"无时区"时间
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return (now - updated_at).total_seconds() > timeout_seconds
