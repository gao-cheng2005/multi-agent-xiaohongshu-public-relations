"""内容业务服务。

给前端"舆情内容"等页面提供数据：笔记列表（带分析和风险等级）、某篇笔记的评论、
筛选条件、整站统计数字、系统运行信息，以及"打开原文"用的链接刷新。

它不直接抓数据，而是从数据库里读已经入库的内容，再加工成前端好用的格式。
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..collectors import OpencliCollector, get_collector
from ..core.llm import llm_gateway
from ..core.settings import settings
from ..repositories.alert_repository import AlertRepository
from ..repositories.analysis_repository import AnalysisRepository
from ..repositories.base import to_dict
from ..repositories.content_repository import ContentRepository
from ..repositories.plan_repository import ResponsePlanRepository
from .alert_service import _level_by_rank, _risk_rank


class ContentService:
    """内容业务服务，负责笔记/评论/统计等查询。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.content_repo = ContentRepository()
        self.analysis_repo = AnalysisRepository()
        self.alert_repo = AlertRepository()
        self.plan_repo = ResponsePlanRepository()

    async def delete_contents(
        self,
        content_id: str | None = None,
        q: str = "",
        source_type: str = "",
        keyword: str = "",
        sentiment: str = "",
        risk: str = "",
        channel: str = "",
        allow_handled: bool = False,
        handled_only: bool = False,
    ) -> int:
        """按条件删除笔记，并级联清理它的评论/分析/预警/方案，返回删除条数。

        所有条件可选；全部为空=删除全部。单条删除只需传 content_id。
        allow_handled 允许删已处理的；handled_only 只删已处理的。
        """
        from ..models import Alert, Analysis, Comment, Content, ResponsePlan

        # 第一步：按筛选条件查出要删的笔记
        statement = (
            select(Content)
            .outerjoin(Analysis, Analysis.content_id == Content.content_id)
            .outerjoin(ResponsePlan, ResponsePlan.content_id == Content.content_id)
        )
        conditions = []
        if not allow_handled:
            # 默认只删"未处理"的（没有方案，或方案状态不是 closed）
            conditions.append(
                or_(ResponsePlan.status.is_(None), ResponsePlan.status != "closed")
            )
        if handled_only:
            conditions.append(ResponsePlan.status == "closed")
        if content_id:
            conditions.append(Content.content_id == content_id)
        if q:
            like = f"%{q.strip()}%"
            conditions.append(or_(Content.title.like(like), Content.author.like(like)))
        if source_type:
            conditions.append(Content.source_type == source_type)
        if keyword:
            conditions.append(Content.keyword == keyword)
        if sentiment:
            conditions.append(Analysis.sentiment == sentiment)
        if risk:
            conditions.append(Analysis.risk_level == risk)
        if channel:
            conditions.append(ResponsePlan.channel == channel)
        if conditions:
            statement = statement.where(and_(*conditions))

        rows = (await self.session.execute(statement)).scalars().all()
        if not rows:
            return 0

        # 第二步：分别取出"数据库主键 id"（删评论/笔记）和"业务编号"（删分析/预警/方案）
        pk_ids = [r.id for r in rows]
        ext_ids = [r.content_id for r in rows]

        # 第三步：取该批笔记的评论编号（因为有的预警挂在评论上）
        comment_ids = [
            c for (c,) in (
                await self.session.execute(
                    select(Comment.comment_id).where(Comment.note_id.in_(ext_ids))
                )
            ).all()
        ]

        # 第四步：按正确的关联关系批量删除（同一个事务里，一步失败整体回滚）
        await self.session.execute(delete(Comment).where(Comment.content_id.in_(pk_ids)))
        await self.session.execute(delete(Analysis).where(Analysis.content_id.in_(ext_ids)))
        await self.session.execute(delete(ResponsePlan).where(ResponsePlan.content_id.in_(ext_ids)))
        await self.session.execute(
            delete(Alert).where(
                or_(Alert.content_id.in_(ext_ids), Alert.content_id.in_(comment_ids))
            )
        )
        await self.session.execute(delete(Content).where(Content.id.in_(pk_ids)))

        # 同步移除话术库索引（失败静默，不阻断删除）
        try:
            from .plan_copy_index import schedule_remove
            schedule_remove(ext_ids)
        except Exception:
            pass

        return len(rows)

    async def list_processed_contents(
        self,
        q: str = "",
        source_type: str = "",
        keyword: str = "",
        sentiment: str = "",
        risk: str = "",
        channel: str = "",
        limit: int = 200,
    ) -> list[dict]:
        """返回"处理记录"：已处理（方案 closed）的笔记列表，支持筛选。"""
        from ..models import Analysis, Content, ResponsePlan
        from ..core.timeutil import format_dt_utc

        statement = (
            select(Content, Analysis, ResponsePlan)
            .join(ResponsePlan, ResponsePlan.content_id == Content.content_id)
            .outerjoin(Analysis, Analysis.content_id == Content.content_id)
            .where(ResponsePlan.status == "closed")
        )
        conditions = []
        if q:
            like = f"%{q.strip()}%"
            conditions.append(or_(Content.title.like(like), Content.author.like(like)))
        if source_type:
            conditions.append(Content.source_type == source_type)
        if keyword:
            conditions.append(Content.keyword == keyword)
        if sentiment:
            conditions.append(Analysis.sentiment == sentiment)
        if risk:
            conditions.append(Analysis.risk_level == risk)
        if channel:
            conditions.append(ResponsePlan.channel == channel)
        if conditions:
            statement = statement.where(and_(*conditions))
        statement = statement.order_by(ResponsePlan.decided_at.desc()).limit(limit)

        rows = (await self.session.execute(statement)).all()
        return [
            {
                "content_id": content.content_id,
                "title": content.title,
                "author": content.author,
                "source_type": content.source_type,
                "keyword": content.keyword,
                "sentiment": analysis.sentiment if analysis else None,
                "risk_level": analysis.risk_level if analysis else None,
                "published_at": format_published_at(content),
                "plan_status": plan.status,
                "plan_channel": plan.channel,
                "plan_reason": plan.reason,
                "handled_at": format_dt_utc(plan.decided_at) if plan.decided_at else "",
                "dm_copy": plan.dm_copy,
                "comment_copy": plan.comment_copy,
                "url": content.url,
            }
            for content, analysis, plan in rows
        ]

    async def list_contents(self, limit: int = 100) -> list[dict]:
        """列出笔记，并为每篇附上最新分析、综合风险等级和方案状态。"""
        rows = await self.content_repo.list_with_latest_analysis(self.session, limit)
        items: list[dict] = []
        for row in rows:
            # 取这篇笔记的最新分析和未处理预警
            analysis = await self.analysis_repo.latest_for_content(self.session, row.content_id)
            alerts = await self.alert_repo.list_by_content(self.session, row.content_id)
            open_alerts = [a for a in alerts if a.status == "open"]

            # 综合风险 = 分析风险 与 未处理预警风险 中更高的那个
            analysis_risk = analysis.risk_level if analysis else "低"
            alert_rank = max((_risk_rank(a.level) for a in open_alerts), default=1)
            rank = max(_risk_rank(analysis_risk), alert_rank)

            # 已处理（方案 closed）的笔记移入"处理记录"，不在这里显示
            plan = await self.plan_repo.get_by_content_id(self.session, row.content_id)
            if plan is not None and plan.status == "closed":
                continue

            data = to_dict(row)
            data.update(
                {
                    "sentiment": analysis.sentiment if analysis else None,
                    "score": analysis.score if analysis else None,
                    "summary": analysis.summary if analysis else "",
                    "risk_level": _level_by_rank(rank),
                    "plan_status": plan.status if plan else None,
                    "plan_channel": plan.channel if plan else None,
                    "plan_reason": plan.reason if plan else "",
                    "published_at": format_published_at(row),
                }
            )
            items.append(data)
        return items

    async def content_filters(self) -> list[dict]:
        """返回去重后的（来源+关键词）组合，供前端下拉筛选使用。"""
        rows = await self.content_repo.list_with_latest_analysis(self.session, 10000)
        seen: set[tuple[str, str]] = set()
        result: list[dict] = []
        for row in rows:
            key = (row.source_type, row.keyword)
            if key not in seen:
                seen.add(key)
                result.append({"source_type": row.source_type, "keyword": row.keyword})
        return sorted(result, key=lambda item: (item["keyword"], item["source_type"]))

    async def list_comments(self, content_id: str) -> list[dict]:
        """返回某篇笔记的评论列表。"""
        rows = await self.content_repo.list_comments(self.session, content_id)
        items = []
        for row in rows:
            d = to_dict(row)
            # 前端按 content 字段渲染正文，这里兼容一下别名
            d["content"] = d.get("text", "") or ""
            # 时间解析不了的（如"昨天""07-30上海"），回退显示原始文案
            if not d.get("published_at"):
                d["published_at"] = (row.raw_json or {}).get("published_at") or ""
            items.append(d)
        return items

    async def stats(self) -> dict:
        """统计整站数据：笔记数、评论数、预警数、处理率、情感与风险分布。"""
        from ..models import Alert, Analysis, Comment, Content, ResponsePlan

        # 各种基础计数
        notes = await self.session.scalar(select(func.count()).select_from(Content))
        comments = await self.session.scalar(select(func.count()).select_from(Comment))
        open_alerts = await self.session.scalar(
            select(func.count()).select_from(Alert).where(Alert.status == "open")
        )
        high_alerts = await self.session.scalar(
            select(func.count())
            .select_from(Alert)
            .where(Alert.status == "open", Alert.level == "高")
        )
        processed_notes = await self.session.scalar(
            select(func.count())
            .select_from(ResponsePlan)
            .where(ResponsePlan.status == "closed")
        )
        handle_rate = round((processed_notes or 0) / notes, 4) if notes else 0.0

        # 待处理/高风险待处理：中高风险且尚未点"完成处理"的笔记数（按笔记去重）
        pending_notes = await self.session.scalar(
            select(func.count(func.distinct(Content.id)))
            .join(Analysis, Analysis.content_id == Content.content_id)
            .outerjoin(ResponsePlan, ResponsePlan.content_id == Content.content_id)
            .where(
                Analysis.risk_level.in_(["中", "高"]),
                or_(ResponsePlan.status.is_(None), ResponsePlan.status != "closed"),
            )
        )
        high_risk_pending_notes = await self.session.scalar(
            select(func.count(func.distinct(Content.id)))
            .join(Analysis, Analysis.content_id == Content.content_id)
            .outerjoin(ResponsePlan, ResponsePlan.content_id == Content.content_id)
            .where(
                Analysis.risk_level == "高",
                or_(ResponsePlan.status.is_(None), ResponsePlan.status != "closed"),
            )
        )

        # 统计情感与风险分布
        analyses = await self.analysis_repo.list_latest(self.session)
        sentiment = Counter(a.sentiment for a in analyses if a.sentiment)
        risk = Counter(a.risk_level for a in analyses if a.risk_level)

        return {
            "notes": notes or 0,
            "comments": comments or 0,
            "open_alerts": open_alerts or 0,
            "high_alerts": high_alerts or 0,
            "processed_notes": processed_notes or 0,
            "handle_rate": handle_rate,
            "pending_notes": pending_notes or 0,
            "high_risk_pending_notes": high_risk_pending_notes or 0,
            "sentiment": dict(sentiment),
            "risk": dict(risk),
        }

    async def recent_pending_notes(self, limit: int = 5) -> list[dict]:
        """最近的中高风险未处理笔记，供总览页"最近预警"展示。"""
        from ..models import Analysis, Content, ResponsePlan

        stmt = (
            select(Content, Analysis)
            .join(Analysis, Analysis.content_id == Content.content_id)
            .outerjoin(ResponsePlan, ResponsePlan.content_id == Content.content_id)
            .where(
                Analysis.risk_level.in_(["中", "高"]),
                or_(ResponsePlan.status.is_(None), ResponsePlan.status != "closed"),
            )
            .order_by(Content.created_at.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            {
                "content_id": content.content_id,
                "title": content.title,
                "author": content.author,
                "sentiment": analysis.sentiment,
                "risk_level": analysis.risk_level,
                "reason": analysis.summary or "",
                "published_at": format_published_at(content),
            }
            for content, analysis in rows
        ]

    async def info(self) -> dict:
        """返回系统运行信息，供设置/关于页展示。"""
        from ..services.llm_config_service import LLMConfigService

        llm_cfg = LLMConfigService(self.session)
        return {
            "collect_mode": "opencli",
            "llm_provider": "siliconflow",
            "llm_model": await llm_cfg.get_current_model(),
            "llm_configured": llm_gateway.configured,
            "sentiment_mode": settings.sentiment_mode,
            "db_path": settings.mysql_database,
            "chroma_host": settings.chroma_host,
        }

    async def refresh_note_url(self, content_id: str) -> str:
        """返回一篇笔记当前可用的打开链接。

        三级策略：先用库存链接验证；失效就重新搜索拿新签名链接；实在不行把库存链接还回去。
        """
        collector = get_collector()
        row = await self.content_repo.get_by_external_id(self.session, content_id)
        if not row:
            raise ValueError("未找到该笔记（可能已被删除）")

        # 快路径：库存链接若还有效，直接返回（避免重新搜索）
        if isinstance(collector, OpencliCollector) and row.url:
            try:
                detail = await asyncio.to_thread(collector.note, row.url)
                if detail and detail.get("content_id") == content_id:
                    return row.url
            except Exception:
                pass

        # 慢路径：重新搜索拿新签名链接
        url = await _fresh_signed_url(self.session, collector, content_id)
        if url:
            return url
        # 兜底：实在拿不到新的，把库存链接还给前端
        if row.url:
            return row.url
        raise ValueError("未找到该笔记的有效链接（可能已被作者删除或改名），请重新采集")


async def _fresh_signed_url(session, collector, content_id: str) -> str | None:
    """通过标题重新搜索，返回一篇笔记带新签名(token)的链接。"""
    if not isinstance(collector, OpencliCollector):
        return None
    row = await ContentRepository().get_by_external_id(session, content_id)
    if not row:
        return None
    keyword = _extract_search_keyword(row.title or "")
    if not keyword:
        return None
    try:
        results = collector.search(keyword, limit=20)
    except Exception:
        return None
    # 在搜索结果里找编号一致的那篇
    for item in results:
        if item.get("content_id") == content_id and item.get("url"):
            return item["url"]
    return None


def _extract_search_keyword(title: str) -> str:
    """从笔记标题里提取一个适合搜索的关键词。

    处理步骤：去掉 #话题标签、去掉标点、只保留前 15 个字。
    """
    text = re.sub(r"#\S+", " ", title or "")
    text = re.sub(r"[\s~～·。，,！!？?（）()【】\[\]：:]+\s*", " ", text).strip()
    text = re.sub(r"\s+", " ", text)[:15]
    return text or (title or "")[:15]


def format_published_at(row) -> str:
    """把笔记发布时间格式化成"YYYY-MM-DD"；空值用链接推导兜底。"""
    from ..core.timeutil import format_dt, published_at_from_xhs_url

    if row.published_at:
        return format_dt(row.published_at, "%Y-%m-%d")
    return published_at_from_xhs_url(row.url or "")
