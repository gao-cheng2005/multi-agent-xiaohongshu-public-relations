"""采集数据落库与联动。

采集流程抓回笔记和评论后，要写进数据库，并自动做情感分析、生成预警、打问题标签。
这个文件就是干这些"收尾工作"的服务：把抓回来的原始数据整理干净、存库，然后触发后续的分析。

它处于采集（collect_service）和分析（workflows）之间，是数据落地的关键一环。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.cleaning import clean_text, dedup_hash, parse_count
from ..core.timeutil import parse_datetime
from ..repositories.alert_repository import AlertRepository
from ..repositories.analysis_repository import AnalysisRepository
from ..repositories.brand_repository import BrandRepository
from ..repositories.content_repository import ContentRepository
from ..repositories.issue_tag_repository import IssueTagRepository
from .agents.sentiment_agent import analyze_risk, analyze_sentiment
from .alert_service import evaluate_alerts


def _build_alerts(content: dict, analysis: dict) -> list[dict]:
    """根据内容和分析结果，生成需要展示的预警列表。

    先按规则（负面、高风险、敏感词）判断；如果整体判为中高风险但没有命中具体规则，
    就补一条"风险提示"预警，保证中高风险内容一定能在预警页看到。
    """
    alerts = evaluate_alerts(content, analysis)
    if not alerts and analysis.get("risk_level") in ("中", "高"):
        alerts = [
            {
                "rule": "风险提示",
                "level": analysis["risk_level"],
                "reason": f"舆情分析判定为{analysis['risk_level']}风险：{analysis.get('summary', '')}",
            }
        ]
    return alerts


class DataAccessService:
    """采集数据的落地服务。

    它把"写笔记""写评论""保存分析结果""生成预警"这些操作收拢在一起，
    采集主流程只需要调用它，不用关心底层细节。
    """

    def __init__(self, session: AsyncSession) -> None:
        # 数据库会话：可以理解成一次"与数据库对话的通道"
        self.session = session
        # 下面几个是负责读写不同表的"数据层"对象
        self.brands = BrandRepository()
        self.content_repo = ContentRepository()
        self.analysis_repo = AnalysisRepository()
        self.alert_repo = AlertRepository()
        self.issue_repo = IssueTagRepository()

    async def upsert_content(self, content: dict):
        """把一篇笔记写入数据库（已存在则更新），返回这条记录。

        思路：先给笔记算出去重指纹，再清洗各字段，最后交给数据层"有则更新、无则新建"。
        """
        # 确定属于哪个品牌（系统只有一个默认品牌）
        brand = await self.brands.get_default(self.session)
        # 计算去重指纹：同一篇笔记（忽略链接参数差异）指纹相同
        content["dedup_hash"] = dedup_hash(content.get("url", ""))
        # 组装待保存的字段：把原始数据清洗/换算成统一格式
        payload = {
            "platform": content.get("platform", "xiaohongshu"),
            "content_id": content.get("content_id", ""),
            "url": (content.get("url", "") or "").strip(),  # 保留完整链接（含签名）
            "author": content.get("author", ""),
            "title": clean_text(content.get("title", "")),
            "body": clean_text(content.get("body", "")),
            "media_type": content.get("media_type", "note"),
            "source_type": content.get("source_type", "keyword"),
            "keyword": content.get("keyword", ""),
            "like_count": parse_count(content.get("like_count")),
            "collect_count": parse_count(content.get("collect_count")),
            "comment_count": parse_count(content.get("comment_count")),
            "share_count": parse_count(content.get("share_count")),
            "view_count": parse_count(content.get("view_count")),
            "published_at": parse_datetime(content.get("published_at")),
            "raw_json": content,  # 原始数据完整保留，方便追溯
            "dedup_hash": content["dedup_hash"],
        }
        return await self.content_repo.create_or_update(self.session, brand.id, payload)

    async def content_exists(self, content: dict) -> bool:
        """判断一篇笔记是否已经入库（按去重指纹判断）。

        多次采集同一产品时，历史采过的笔记应直接跳过；
        指纹基于去掉参数后的链接，所以链接签名变了也能识别为同一篇。
        """
        return (
            await self.content_repo.get_by_dedup_hash(
                self.session, dedup_hash(content.get("url", ""))
            )
        ) is not None

    async def add_comment(self, comment: dict, content_id=None) -> None:
        """把一条评论写入数据库；按（笔记编号 + 评论编号）去重。

        content_id 是笔记在数据库里的主键，必须由调用方传进来，否则存不进去。
        """
        note_id = comment.get("note_id", "")
        comment_id = str(comment.get("comment_id", ""))
        # 重复采集时同一批评论会重复出现，先查一下避免重复入库
        if await self.content_repo.get_comment(self.session, note_id, comment_id):
            return
        brand = await self.brands.get_default(self.session)
        payload = {
            "content_id": content_id or comment.get("content_id"),
            "note_id": note_id,
            "comment_id": comment_id,
            "parent_id": comment.get("parent_id"),  # 有值表示是回复
            "author": comment.get("author", ""),
            "text": clean_text(comment.get("content", "")),
            "like_count": parse_count(comment.get("like_count")),
            "published_at": parse_datetime(comment.get("published_at")),
            "raw_json": comment,
        }
        await self.content_repo.add_comment(self.session, brand.id, payload)

    async def analyze_and_alert(
        self,
        content: dict,
        external_content_id: str,
        comments: list[dict] | None = None,
    ) -> dict:
        """对一篇笔记做情感+风险分析，并把分析结果和预警一起落库。

        这是"一步到位"的老路径：先调两个分析，再保存分析、生成预警。
        """
        brand = await self.brands.get_default(self.session)
        # 两个独立分析：情感（标题+正文）、风险（评论+互动数据）
        sentiment_result = await analyze_sentiment(content)
        risk_result = await analyze_risk(content, comments or [])
        # 组装成统一的"分析"记录
        analysis = {
            "sentiment": sentiment_result.get("sentiment", "中性"),
            "confidence": sentiment_result.get("confidence", 0.5),
            "risk_level": risk_result.get("risk_level", "低"),
            "score": risk_result.get("score", 0) or 0,
            "summary": risk_result.get("summary", ""),
            "topics": [],
            "keywords": [],
            "model": f"{sentiment_result.get('model', 'rule')}+{risk_result.get('model', 'rule')}",
        }
        # 保存最新分析（旧的会被替换）
        await self.analysis_repo.replace_for_content(
            self.session, brand.id, external_content_id, analysis
        )
        # 根据分析结果生成并保存预警
        await self.alert_repo.replace_for_content(
            self.session, brand.id, external_content_id, _build_alerts(content, analysis)
        )
        return analysis

    async def apply_analysis_and_alerts(
        self, content: dict, external_content_id: str, analysis: dict
    ) -> None:
        """把（流程节点产出的）分析结果落库，并生成对应预警。

        与上面不同，这个方法只负责"落地"，分析本身由流程节点完成。
        落库前会做字段过滤，只保存分析表允许的字段。
        """
        # 分析表只接受规定字段，多维中间量不持久化
        allowed = {"sentiment", "confidence", "risk_level", "score", "summary", "topics", "keywords", "model"}
        analysis = {k: v for k, v in (analysis or {}).items() if k in allowed}
        brand = await self.brands.get_default(self.session)
        await self.analysis_repo.replace_for_content(
            self.session, brand.id, external_content_id, analysis
        )
        await self.alert_repo.replace_for_content(
            self.session, brand.id, external_content_id, _build_alerts(content, analysis)
        )

    async def tag_content(self, content_id: str, product: str) -> None:
        """给一篇笔记打问题标签（走采集后处理流程里的"标签抽取"阶段）。

        无产品归属（如按链接采集）时不打标，避免数据散落到空产品下。
        """
        from ..repositories.base import to_dict
        from .workflows.post_collect_workflow import build_post_collect_workflow

        if not (product or "").strip():
            return None
        row = await self.content_repo.get_by_external_id(self.session, content_id)
        if row is None:
            return None
        comments = await self.content_repo.list_comments(self.session, content_id)
        brand = await self.brands.get_default(self.session)

        # 这是流程节点回调：把抽取出的问题标签整批写入数据库
        async def store_tags(cid: str, prod: str, items: list[dict]) -> None:
            await self.issue_repo.replace_for_content(self.session, brand.id, prod, cid, items)

        workflow = build_post_collect_workflow(store_tags=store_tags)
        await workflow.ainvoke(
            {
                "phase": "issues",
                "content_id": content_id,
                "product": product,
                "content": {"title": row.title, "body": row.body},
                "comments": [to_dict(c) for c in comments],
            }
        )
        return None
