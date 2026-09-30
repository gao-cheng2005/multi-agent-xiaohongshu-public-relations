"""预警业务。

负责三件事：根据分析结果判断要不要生成预警（规则函数）；把预警按笔记汇总展示；
把预警标记为已处理（单条或按笔记整批）。

预警是"提醒运营人员去处理"的记录，本身不会自动评论或私信，需要人工介入。
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.cleaning import clean_text, is_negated
from ..core.timeutil import utcnow
from ..models import Alert
from ..repositories.alert_repository import AlertRepository
from ..repositories.analysis_repository import AnalysisRepository
from ..repositories.content_repository import ContentRepository
from .agents.sentiment_agent import SENSITIVE_WORDS

logger = logging.getLogger("alert")


def _risk_rank(level: str | None) -> int:
    """把风险等级转成数字，方便比较大小：高=3，中=2，其他=1。"""
    return {"高": 3, "中": 2}.get(level or "", 1)


def _level_by_rank(rank: int) -> str:
    """把数字等级转回文字：3=高，2=中，其他=低。"""
    return {3: "高", 2: "中"}.get(rank, "低")


def evaluate_alerts(content: dict, analysis: dict) -> list[dict]:
    """根据内容和分析结果，判断该生成哪些预警，按规则名去重返回。

    三条规则：负面情感→中风险；高风险→高风险；命中敏感词→高风险
    （若大模型判为正面/低风险则降为中）。注意排除否定语境，如"不用避雷"。
    """
    text = clean_text(f"{content.get('title', '')} {content.get('body', '')}")
    sentiment = analysis.get("sentiment", "中性")
    level = analysis.get("risk_level", "低")
    alerts: list[dict] = []

    # 规则 1：情感为负面
    if sentiment == "负面":
        alerts.append(
            {
                "rule": "负面情感",
                "level": "中",
                "reason": f"内容情感判定为负面，置信度 {analysis.get('confidence', 0)}",
            }
        )
    # 规则 2：整体被判为高风险
    if level == "高":
        alerts.append({"rule": "高风险内容", "level": "高", "reason": "分析判定为高风险内容"})

    # 规则 3：命中敏感词（排除否定语境）
    hit_words = [w for w in SENSITIVE_WORDS if w in text and not is_negated(text, w)]
    if hit_words:
        llm_positive = level == "低" and sentiment == "正面"
        alerts.append(
            {
                "rule": "敏感词命中",
                "level": "中" if llm_positive else "高",
                "reason": f"命中敏感词：{', '.join(hit_words)}"
                + ("（LLM 判定正面/低风险，降级为中）" if llm_positive else ""),
            }
        )
    return list({item["rule"]: item for item in alerts}.values())


class AlertService:
    """预警业务服务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.alert_repo = AlertRepository()
        self.content_repo = ContentRepository()
        self.analysis_repo = AnalysisRepository()

    async def list_alerts(self, status: str | None = None) -> list[dict]:
        """把预警按笔记聚合展示，只保留中高风险，按风险从高到低排序。

        每篇笔记一行，展示该笔记的最高风险等级、命中规则和待处理条数。
        """
        contents = await self.content_repo.list_with_latest_analysis(self.session, 10000)
        alerts = await self.alert_repo.list_all(self.session)

        # 把预警按笔记分组，并丢弃没有对应笔记的"孤儿预警"
        content_ids = {c.content_id for c in contents}
        alert_by_content: dict[str, list[Alert]] = defaultdict(list)
        for alert in alerts:
            if alert.content_id in content_ids:
                alert_by_content[alert.content_id].append(alert)

        result: list[dict] = []
        for content in contents:
            owned = alert_by_content.get(content.content_id, [])
            if not owned:
                continue

            # 取最高风险等级，低于"中"的忽略（不展示低风险）
            max_rank = max(_risk_rank(item.level) for item in owned)
            if max_rank < 2:
                continue

            # 统计待处理条数，确定整篇的展示状态
            open_count = sum(1 for item in owned if item.status == "open")
            row_status = "open" if open_count else "handled"
            if status == "open" and open_count == 0:
                continue
            if status == "handled" and open_count > 0:
                continue

            analysis = await self.analysis_repo.latest_for_content(self.session, content.content_id)
            level_name = _level_by_rank(max_rank)
            result.append(
                {
                    "note_id": content.content_id,
                    "source_type": content.source_type,
                    "keyword": content.keyword,
                    "note_title": content.title,
                    "note_sentiment": analysis.sentiment if analysis else None,
                    "note_risk_level": level_name,
                    "level": level_name,
                    "rules": ",".join({item.rule for item in owned}),
                    "open_count": open_count,
                    "alert_id": str(max(item.id for item in owned)),
                    "status": row_status,
                }
            )

        result.sort(key=lambda item: (_risk_rank(item["level"]), item["note_id"]), reverse=True)
        return result

    async def handle(self, alert_id: uuid.UUID, status: str = "handled") -> None:
        """把某一条预警标记为已处理。"""
        logger.info("预警标记已处理 alert_id=%s status=%s", alert_id, status)
        await self.alert_repo.handle_by_ids(self.session, [alert_id], status, utcnow())

    async def handle_note(self, note_id: str, status: str = "handled") -> int:
        """把某笔记及其评论关联的预警全部标记处理，返回处理条数。"""
        logger.info("按笔记标记预警已处理 note_id=%s status=%s", note_id, status)
        # 评论也可能触发预警，所以先取这篇笔记的评论编号
        comments = await self.content_repo.list_comments(self.session, note_id)
        comment_ids = [item.comment_id for item in comments]

        # 查出笔记本身 + 它评论关联的所有预警
        result = await self.session.execute(
            select(Alert).where(
                or_(Alert.content_id == note_id, Alert.content_id.in_(comment_ids))
            )
        )
        alerts = list(result.scalars().all())
        logger.info("按笔记标记预警 note_id=%s 共关联=%s 条", note_id, len(alerts))
        return await self.alert_repo.handle_by_ids(
            self.session, [item.id for item in alerts], status, utcnow()
        )
