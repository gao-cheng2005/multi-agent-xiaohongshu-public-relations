"""采集主流程。

这是"采集"这件事的核心编排逻辑：根据用户选择（关键词或笔记链接）去平台抓笔记，
再逐篇补详情、存库、抓评论、做分析预警，中高风险时自动生成应对方案，最后统计结果返回。

抓取本身很耗时（要驱动浏览器），所以底层用线程执行；分析、方案生成等后续步骤
用后台任务异步跑，避免拖慢整个采集过程。
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..collectors import OpencliCollector, get_collector
from ..core.cleaning import dedup_hash
from ..models import Alert
from .content_service import _fresh_signed_url
from .data_access_service import DataAccessService
from .keyword_service import KeywordService

logger = logging.getLogger("collect")

# 后台任务的并发上限：限制同时跑几个大模型调用，避免资源被挤爆
_PLAN_SEMAPHORE = asyncio.Semaphore(2)
_TAG_SEMAPHORE = asyncio.Semaphore(2)
_REPORT_SEMAPHORE = asyncio.Semaphore(1)


class NoCollectableDataError(RuntimeError):
    """采集工具本身正常，但确实没采到任何新内容时抛出的异常。"""


async def _schedule_issue_tag(content_id: str, product: str) -> None:
    """后台给一篇笔记打问题标签，并顺带刷新该产品的优化建议。

    用独立数据库会话执行，避免主请求的会话结束导致任务失败；
    内部异常一律吞掉，不影响采集主流程。
    """
    from ..db.session import SessionLocal

    async with _TAG_SEMAPHORE:
        try:
            async with SessionLocal() as session:
                await DataAccessService(session).tag_content(content_id, product)
                await session.commit()
            # 打标完成后，自动触发该产品的优化建议重新生成
            asyncio.get_running_loop().create_task(_schedule_product_report(product))
        except Exception:
            pass


async def _schedule_product_report(product: str) -> None:
    """后台生成/更新某产品的优化建议报告。"""
    from ..db.session import SessionLocal
    from .analytics_service import AnalyticsService

    async with _REPORT_SEMAPHORE:
        try:
            async with SessionLocal() as session:
                await AnalyticsService(session).generate_product_report(product)
                await session.commit()
        except Exception:
            logging.getLogger("collect.report").error(
                "product report generation failed for %s", product, exc_info=True
            )


async def _schedule_plan(content_id: str) -> None:
    """后台生成一篇笔记的应对方案。

    用独立会话执行，避免主请求结束导致方案没生成；失败只记日志不中断采集。
    """
    from ..db.session import SessionLocal
    from .plan_service import PlanService

    async with _PLAN_SEMAPHORE:
        try:
            async with SessionLocal() as session:
                await PlanService(session).schedule_generation(content_id)
                await session.commit()
        except Exception:
            logging.getLogger("collect.plan").error(
                "async plan generation failed for %s", content_id, exc_info=True
            )


class CollectService:
    """采集业务服务，把整条采集链路串起来。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.data_access = DataAccessService(session)
        self.keywords = KeywordService(session)

    async def collect(
        self,
        keyword: str | None = None,
        note_url: str | None = None,
        limit: int = 10,
        fetch_comments: bool = True,
        comment_depth: int = 3,
    ) -> dict:
        """执行一次完整采集，返回统计结果。

        keyword 和 note_url 二选一；limit 是关键词模式想采的条数；
        fetch_comments 控制要不要抓评论，comment_depth 是每条笔记抓几条顶层评论。
        """
        collector = get_collector()
        contents: list[dict] = []
        skipped_notes = 0
        logger.info(
            "开始采集 mode=%s keyword=%r note_url=%r limit=%s",
            "note_url" if note_url else ("keyword" if keyword else "none"),
            keyword, note_url, limit,
        )

        # 第一步：按用户选择的方式抓一批笔记
        if note_url:
            contents = await self._collect_by_url(collector, note_url)
        elif keyword:
            contents, skipped_notes = await self._search_new_notes(collector, keyword, limit)
            await self.keywords.create(keyword)
            await self.keywords.mark_triggered(keyword)
        else:
            raise ValueError("需要提供 keyword 或 note_url 之一")

        # 完全没采到新内容时给出明确提示（只是跳过一批已入库的不算失败）
        if not contents and skipped_notes == 0:
            target = keyword or note_url or ""
            raise NoCollectableDataError(
                f"OpenCLI 未返回任何笔记：{target}。"
                "请确认关键词有效、Chrome 已登录小红书，或改用包含 xsec_token 的完整笔记链接。"
            )

        collected_notes = 0
        collected_comments = 0

        # 第二步：逐篇处理每一篇笔记
        for content in contents:
            content["source_type"] = "keyword" if keyword else "note_url"
            content["keyword"] = keyword or ""
            logger.info(
                "开始处理笔记 id=%s 标题=%s",
                content.get("content_id"), (content.get("title") or "")[:40],
            )

            # 关键词搜索返回的信息较简略，再抓一次详情补齐
            if not note_url and isinstance(collector, OpencliCollector) and content.get("url"):
                try:
                    detail = await asyncio.to_thread(collector.note, content["url"])
                    content.update({k: v for k, v in detail.items() if v})
                except Exception:
                    pass

            # 历史去重：采过的笔记直接跳过，不再更新/分析
            if await self.data_access.content_exists(content):
                skipped_notes += 1
                logger.info("笔记已存在，跳过 id=%s", content.get("content_id"))
                continue

            # 存库，拿到数据库主键 id（后面关联评论要用）
            external_content_id = str(content.get("content_id") or "")
            content_row = await self.data_access.upsert_content(content)
            collected_notes += 1

            # 抓评论（可选）：失败只记日志，不阻断笔记入库
            fetched_comments: list[dict] = []
            if fetch_comments and content.get("url"):
                await asyncio.sleep(1)  # 笔记之间留间隔，避免触发风控
                try:
                    fetched_comments = await asyncio.to_thread(
                        collector.comments, content["url"], comment_depth
                    )
                except Exception as exc:
                    logging.getLogger("collect.comments").warning(
                        "评论抓取失败（跳过）：%s，原因=%s", external_content_id, exc
                    )
                    fetched_comments = []
                for comment in fetched_comments:
                    await self.data_access.add_comment(comment, content_id=content_row.id)
                    collected_comments += 1

            # 分析：走采集后处理流程（情感 → 风险 → 落库分析与预警）
            await self._analyze(content, external_content_id, fetched_comments)
            await self.session.commit()

            # 第三步：异步调度后台任务（问题标签 + 应对方案）
            asyncio.get_running_loop().create_task(
                _schedule_issue_tag(external_content_id, content.get("keyword") or "")
            )
            asyncio.get_running_loop().create_task(_schedule_plan(external_content_id))

        # 第四步：统计当前待处理预警总数并返回
        open_alerts = await self.session.scalar(
            select(func.count()).select_from(Alert).where(Alert.status == "open")
        )
        logger.info(
            "本次采集完成：新入库笔记=%s 评论=%s 跳过=%s 待处理预警=%s",
            collected_notes, collected_comments, skipped_notes, open_alerts or 0,
        )
        return {
            "collected_notes": collected_notes,
            "collected_comments": collected_comments,
            "skipped_notes": skipped_notes,
            "open_alerts": open_alerts or 0,
            "collect_mode": "opencli",
        }

    async def _collect_by_url(self, collector, note_url: str) -> list[dict]:
        """按笔记链接采集；链接签名失效时尝试重新搜索补一条新链接。"""
        try:
            note_id = urlparse(note_url).path.rstrip("/").split("/")[-1]
        except Exception:
            note_id = ""

        try:
            return [await asyncio.to_thread(collector.note, note_url)]
        except Exception as exc:
            # 直接抓失败（常见：链接里没有有效签名），尝试重新搜索拿新鲜链接
            fresh = await _fresh_signed_url(self.session, collector, note_id) if note_id else None
            if fresh:
                return [await asyncio.to_thread(collector.note, fresh)]
            raise RuntimeError(
                "笔记URL缺少有效的 xsec_token（登录态签名链接）。"
                "请从小红书页面复制含 xsec_token 参数的完整链接，"
                "或先通过关键词采集到该笔记后重试。"
            ) from exc

    async def _analyze(self, content: dict, external_content_id: str, comments: list[dict]) -> None:
        """对单篇笔记执行分析流程并落库；失败只记日志，不中断整批采集。"""
        from .workflows.post_collect_workflow import build_post_collect_workflow

        # 这是流程节点回调：把分析结果写库并生成预警
        async def store_analysis(state) -> None:
            await self.data_access.apply_analysis_and_alerts(
                state.get("content") or {},
                external_content_id,
                state.get("analysis") or {},
            )

        workflow = build_post_collect_workflow(store_analysis=store_analysis, store_tags=None)
        try:
            await workflow.ainvoke(
                {
                    "phase": "analyze",
                    "content_id": external_content_id,
                    "product": content.get("keyword") or "",
                    "content": content,
                    "comments": comments,
                }
            )
        except Exception:
            logging.getLogger("collect.analyze").error(
                "analyze failed for %s", external_content_id, exc_info=True
            )

    async def _search_new_notes(self, collector, keyword: str, wanted: int) -> tuple[list[dict], int]:
        """按关键词搜索，过滤掉已入库/批内重复，尽量凑够 wanted 条新笔记。

        搜索没有分页，只能靠放大窗口往后补采；窗口有上限，凑不满就返回已拿到的新笔记。
        返回 (新笔记列表, 跳过的已入库重复条数)。
        """
        wanted = max(1, int(wanted))
        window = max(wanted, 10)
        max_window = max(50, wanted)
        collected: list[dict] = []
        seen: set[str] = set()
        skipped = 0
        search_error: Exception | None = None

        # 循环搜索并扩大窗口，直到凑够或没有更多结果
        while len(collected) < wanted and window <= max_window:
            try:
                rows = await asyncio.to_thread(collector.search, keyword, window)
            except Exception as exc:
                search_error = exc
                break
            if not rows:
                break

            for content in rows:
                url = (content.get("url") or "").strip()
                # 无链接的结果没法入库，直接忽略
                if not url:
                    continue
                h = dedup_hash(url)
                # 批内已处理过的（已入库或已选），不再重复查询/计数
                if h in seen:
                    continue
                seen.add(h)
                # 已入库：跳过并计数
                if await self.data_access.content_exists(content):
                    skipped += 1
                    continue
                collected.append(content)
                if len(collected) >= wanted:
                    break

            if len(collected) >= wanted or len(rows) < window:
                break
            # 不够：放大窗口继续往深处补采
            new_window = min(window * 2, max_window)
            if new_window == window:
                break
            window = new_window

        # 一条都没采到且搜索本身报错：抛真实原因，而不是笼统的"没结果"
        if not collected and search_error is not None:
            raise search_error
        return collected, skipped
