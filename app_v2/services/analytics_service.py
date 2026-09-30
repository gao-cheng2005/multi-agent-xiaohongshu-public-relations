"""统计与效果分析。

给"数据分析"页面提供数据：情感趋势（近 N 天每天正/中/负面各多少）、热词排行、
方案与预警的处理效果指标，以及产品维度的用户问题分析和优化建议报告。

所有指标都是实时从数据库里算出来的，不保存历史报表文件。
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.timeutil import format_dt_utc
from ..repositories.analysis_repository import AnalysisRepository
from ..repositories.base import to_dict
from ..repositories.brand_repository import BrandRepository
from ..repositories.content_repository import ContentRepository
from ..repositories.issue_tag_repository import IssueTagRepository
from ..repositories.plan_repository import ResponsePlanRepository
from ..repositories.product_report_repository import ProductReportRepository

logger = logging.getLogger("analytics")


def _parse_time(value) -> datetime | None:
    """把常见格式的时间转成标准时间对象，转不了返回空。

    用于计算方案从创建到决策的耗时。
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


class AnalyticsService:
    """统计与效果分析服务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.content_repo = ContentRepository()
        self.analysis_repo = AnalysisRepository()
        self.plan_repo = ResponsePlanRepository()
        self.issue_repo = IssueTagRepository()
        self.report_repo = ProductReportRepository()

    async def trend(self, days: int = 30) -> dict:
        """近 N 天每天各情感的数量序列，供折线图使用。"""
        days = max(1, min(int(days), 365))
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)

        # 取出全部笔记，按天、按情感分组计数
        contents = await self.content_repo.list_with_latest_analysis(self.session, 100000)
        by_day: dict[str, Counter] = {}
        for content in contents:
            created = content.created_at
            if not created or created.replace(tzinfo=timezone.utc) < start:
                continue
            analysis = await self.analysis_repo.latest_for_content(self.session, content.content_id)
            sentiment = analysis.sentiment if analysis else "中性"
            by_day.setdefault(created.strftime("%Y-%m-%d"), Counter())[sentiment] += 1

        # 生成完整日期序列，中间缺的日期补 0
        day_list = [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
        series = {"正面": [], "中性": [], "负面": []}
        for day in day_list:
            data = by_day.get(day, Counter())
            for key in series:
                series[key].append(data.get(key, 0))
        return {
            "days": day_list,
            "series": [{"name": key, "data": values} for key, values in series.items()],
        }

    async def overview_trend(self, days: int = 7, product: str = "") -> dict:
        """近 N 天每天采集笔记数 + 中高风险笔记数，可按产品过滤。"""
        from ..models import Analysis, Content

        days = max(1, min(int(days), 90))
        local_tz = timezone(timedelta(hours=8))
        today = datetime.now(timezone.utc).astimezone(local_tz).date()
        day_list = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days - 1, -1, -1)]

        stmt = select(Content.created_at, Analysis.risk_level).outerjoin(
            Analysis, Analysis.content_id == Content.content_id
        )
        if product:
            stmt = stmt.where(Content.keyword == product)
        rows = (await self.session.execute(stmt)).all()

        by_day: dict[str, dict] = {}
        for created, risk in rows:
            if not created:
                continue
            bucket = by_day.setdefault(format_dt_utc(created, "%Y-%m-%d"), {"notes": 0, "medium": 0, "high": 0})
            bucket["notes"] += 1
            if risk == "中":
                bucket["medium"] += 1
            elif risk == "高":
                bucket["high"] += 1

        items = [
            {
                "date": d,
                "notes": by_day.get(d, {}).get("notes", 0),
                "medium_high": by_day.get(d, {}).get("medium", 0) + by_day.get(d, {}).get("high", 0),
                "medium": by_day.get(d, {}).get("medium", 0),
                "high": by_day.get(d, {}).get("high", 0),
            }
            for d in day_list
        ]
        return {"days": day_list, "items": items}

    async def hotwords(self, limit: int = 20) -> list[dict]:
        """统计问题标签（用户原话）出现频次，返回前 limit 个。"""
        labels = await self.issue_repo.list_labels(self.session)
        counter: Counter = Counter()
        for label in labels:
            if isinstance(label, str) and label.strip():
                counter[label.strip()] += 1
        return [
            {"word": word, "count": count}
            for word, count in counter.most_common(min(limit, 100))
        ]

    async def effect(self) -> dict:
        """方案与预警的处理效果指标。"""
        from ..models import Alert

        # 方案维度：总数、待审核、已采纳、已关闭、采纳率
        plans = await self.plan_repo.list(self.session)
        total = len(plans)
        pending = sum(1 for p in plans if p.status == "pending")
        accepted = sum(1 for p in plans if p.status == "accepted")
        closed = sum(1 for p in plans if p.status == "closed")
        decided = accepted + closed
        adoption_rate = round(accepted / decided, 4) if decided else 0.0

        # 已决策方案的平均决策耗时（秒）
        latencies = []
        for p in plans:
            if p.status in ("accepted", "closed"):
                started = _parse_time(p.created_at)
                finished = _parse_time(p.decided_at)
                if started and finished and finished >= started:
                    latencies.append((finished - started).total_seconds())
        avg_decision_seconds = round(sum(latencies) / len(latencies), 1) if latencies else 0.0

        # 预警维度：总数、待处理、已处理、处理率
        alerts_total = await self.session.scalar(select(func.count()).select_from(Alert)) or 0
        alerts_open = await self.session.scalar(
            select(func.count()).select_from(Alert).where(Alert.status == "open")
        ) or 0
        alerts_handled = alerts_total - alerts_open
        alert_handle_rate = round(alerts_handled / alerts_total, 4) if alerts_total else 0.0

        return {
            "plans_total": total,
            "plans_pending": pending,
            "plans_accepted": accepted,
            "plans_closed": closed,
            "adoption_rate": adoption_rate,
            "avg_decision_seconds": avg_decision_seconds,
            "alerts_total": alerts_total,
            "alerts_open": alerts_open,
            "alerts_handled": alerts_handled,
            "alert_handle_rate": alert_handle_rate,
        }

    async def product_analysis(self, product: str) -> dict:
        """单个产品的用户问题分析：概览 + 维度统计 + 待确认维度。"""
        from ..models import Content, IssueTag

        data = await self.issue_repo.aggregate_by_product(self.session, product)
        dims = data["dimensions"]
        note_count = await self.session.scalar(
            select(func.count()).select_from(Content).where(Content.keyword == product)
        )
        tagged_notes = await self.session.scalar(
            select(func.count(func.distinct(IssueTag.content_id))).where(IssueTag.product == product)
        )
        return {
            "product": product,
            "notes": note_count or 0,
            "tagged_notes": tagged_notes or 0,
            "total_tags": sum(d["count"] for d in dims),
            "top_dimension": dims[0] if dims else None,
            "dimensions": dims,
            "unconfirmed": await self.issue_repo.unconfirmed_dimensions(self.session, product),
        }

    async def generate_product_report(self, product: str) -> dict:
        """报表智能体：把产品的问题聚合数据整理成一份优化建议报告。"""
        from .workflows.issue_analysis_workflow import build_report_workflow

        # 先把问题统计拼成文字，交给报表智能体
        data = await self.issue_repo.aggregate_by_product(self.session, product)
        lines = [f"产品：{product}\n问题统计："]
        for d in data["dimensions"]:
            neg_pct = round(d["negative"] / d["count"] * 100) if d["count"] else 0
            lines.append(
                f"- {d['dimension']}: {d['count']}次（负面占比{neg_pct}%），"
                f"常见说法：{'、'.join(d['labels']) or '无'}；样例：{d['sample_excerpt']}"
            )
        unconfirmed = await self.issue_repo.unconfirmed_dimensions(self.session, product)
        lines.append("待确认新维度：" + ("、".join(u["dimension"] for u in unconfirmed) if unconfirmed else "无"))

        state = await build_report_workflow().ainvoke({"payload": "\n".join(lines)})
        report = state.get("report") or {}
        # 生成后缓存（一个产品一份），页面打开直接读，不重复生成
        if report:
            brand = await BrandRepository().get_default(self.session)
            await self.report_repo.upsert(self.session, brand.id, product, report)
            logger.info("产品优化报告已生成并缓存 product=%s", product)
        else:
            logger.warning("产品优化报告生成失败（图为空输出）product=%s", product)
        return report

    async def get_product_report(self, product: str) -> dict | None:
        """读取产品优化建议缓存；无则返回 None。"""
        row = await self.report_repo.get(self.session, product)
        return row.report if row else None

    async def merge_dimensions(self, product: str) -> dict:
        """归并待确认维度：归并智能体给出方案，按结果落库。"""
        from .workflows.issue_analysis_workflow import build_merge_workflow

        confirmed = await self.issue_repo.aggregate_by_product(self.session, product)
        existing = [d["dimension"] for d in confirmed["dimensions"]]
        unconfirmed = await self.issue_repo.unconfirmed_dimensions(self.session, product)

        payload_lines = ["正式维度：", *[f"- {d}" for d in existing], "待确认新维度："]
        payload_lines += [
            f"- {u['dimension']}（定义：{u['dimension_def'] or '无'}，出现{u['count']}次）"
            for u in unconfirmed
        ]

        state = await build_merge_workflow().ainvoke({"payload": "\n".join(payload_lines)})
        applied = []
        for m in state.get("merges") or []:
            from_dim = (m.get("from_dim") or "").strip()
            into_dim = (m.get("into_dim") or "").strip()
            if not from_dim:
                continue
            if into_dim and into_dim != from_dim:
                # 有归并目标：改名归并
                await self.issue_repo.rename_dimension(self.session, from_dim, into_dim)
                applied.append({"from": from_dim, "into": into_dim})
            else:
                # 无归并目标：确认保留为新维度
                await self.issue_repo.set_confirmed(self.session, from_dim, True, product)
                applied.append({"from": from_dim, "into": from_dim})
        return {
            "merged": applied,
            "remaining_unconfirmed": await self.issue_repo.unconfirmed_dimensions(self.session, product),
        }

    async def confirm_dimension(self, product: str, dimension: str, confirmed: bool = True) -> int:
        """人工确认（或忽略）一个待确认维度。"""
        return await self.issue_repo.set_confirmed(self.session, dimension, confirmed, product)
