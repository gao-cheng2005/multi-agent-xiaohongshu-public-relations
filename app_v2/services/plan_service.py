"""应对方案业务。

负责生成、查询、决策和处理应对方案。方案由大模型生成，包含舆情摘要、推荐动作、
私信文案和公开评论文案；生成后需要人工审核，采纳或关闭，再线下到平台执行。

这个服务是"生成方案"这件事的编排层：读取笔记和分析结果，交给方案流程去跑，再落库。
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.timeutil import utcnow
from ..repositories.analysis_repository import AnalysisRepository
from ..repositories.base import to_dict
from ..repositories.brand_repository import BrandRepository
from ..repositories.content_repository import ContentRepository
from ..repositories.plan_repository import ResponsePlanRepository
from .plan_copy_index import _load_dimensions

logger = logging.getLogger("plan")


class PlanService:
    """应对方案业务服务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.brands = BrandRepository()
        self.content_repo = ContentRepository()
        self.analysis_repo = AnalysisRepository()
        self.plan_repo = ResponsePlanRepository()

    async def schedule_generation(self, content_id: str, force: bool = False) -> None:
        """生成方案的统一入口（自动/手动共用）。

        force=False 表示自动：正面/中性 + 低风险会跳过生成，省成本；
        force=True 表示手动点按钮：跳过"无需处理"判断，强制生成。
        失败时会把方案状态置为 failed，避免前端永远显示"生成中"。
        """
        try:
            logger.info("方案生成开始 content_id=%s force=%s", content_id, force)
            await self._do_generation(content_id, force=force)
            logger.info("方案生成完成 content_id=%s", content_id)
        except Exception as exc:
            logger.warning("方案生成异常 content_id=%s：%s", content_id, exc)
            try:
                row = await self.plan_repo.get_by_content_id(self.session, content_id)
                if row and row.status in ("pending", "processing"):
                    await self.plan_repo.mark_status(self.session, row.id, "failed")
            except Exception:
                pass

    async def _do_generation(
        self, content_id: str, human_feedback: str = "", force: bool = False
    ) -> None:
        """真正执行方案生成：读取笔记与分析，跑方案流程，写入结果。"""
        from .agents.decision import should_generate
        from .workflows.planning_workflow import PlanState, build_planning_workflow

        note = await self.content_repo.get_by_external_id(self.session, content_id)
        if note is None:
            logger.warning("方案生成：笔记不存在 content_id=%s", content_id)
            return None

        # 取最新分析结果，得到情感和风险等级
        analysis = await self.analysis_repo.latest_for_content(self.session, content_id)
        sentiment = analysis.sentiment if analysis else "中性"
        risk_level = analysis.risk_level if analysis else "低"
        brand = await self.brands.get_default(self.session)
        comments = await self.content_repo.list_comments(self.session, content_id)

        # 自动生成时：正面/中性 + 低风险直接记 skipped（无需处理）
        if not force and not should_generate(sentiment, risk_level):
            row = await self.plan_repo.upsert(
                self.session, brand.id, content_id, "auto",
                {"channel": "skip", "summary": "正面/中性且低风险，无需处理"},
            )
            await self.plan_repo.mark_status(self.session, row.id, "skipped")
            logger.info("无需处理短路 content_id=%s -> skipped", content_id)
            return None

        # 需要生成：先落一个 processing 占位，防止并发重复生成，也方便前端提示"生成中"
        pending = await self.plan_repo.upsert(self.session, brand.id, content_id, "auto", {})
        await self.plan_repo.mark_status(self.session, pending.id, "processing")

        # 加载问题维度（供文案生成时检索历史参考文案）
        dimensions = await _load_dimensions(self.session, content_id)
        logger.info("开始执行方案图 content_id=%s 维度=%s", content_id, dimensions)

        # 这是流程收尾节点的回调：把最终方案写进数据库
        async def store_plan(state: PlanState) -> None:
            channel = state.get("channel") or "public"
            channel_label = {"dm": "私信", "public": "公开评论", "skip": "无需处理"}.get(channel, "公开评论")
            draft = state.get("draft_text", "")
            plan = {
                "channel": channel,
                "summary": f"渠道：{channel_label}；原因：{state.get('reason', '')}",
                "recommended_action": state.get("reason", ""),
                "reason": state.get("reason", ""),
                "dm_copy": draft if channel == "dm" else "",
                "comment_copy": draft if channel == "public" else "",
            }
            row = await self.plan_repo.upsert(self.session, brand.id, content_id, "auto", plan)
            await self.plan_repo.mark_status(self.session, row.id, "done")

        workflow = build_planning_workflow(store_plan=store_plan)
        await workflow.ainvoke(
            {
                "content_id": content_id,
                "human_feedback": human_feedback,
                "title": note.title,
                "body": note.body,
                "comments": [to_dict(c) for c in comments],
                "sentiment": sentiment,
                "risk_level": risk_level,
                "risk_reason": analysis.summary if analysis else "",
                "urgent": False,
                "published_at": str(note.published_at) if note.published_at else "",
                "analysis": to_dict(analysis) if analysis else {},
                "dimensions": dimensions,
            }
        )
        logger.info("方案图执行完成 content_id=%s", content_id)
        return None

    async def reset_stale_processing(self, timeout_seconds: int = 600) -> int:
        """把卡在"处理中"过久的记录重置为失败。

        场景：进程重启后，正在跑的生成任务中断，状态会永远停在 processing；
        这里识别这些记录并转成 failed，让前端能重试。
        """
        from .agents.decision import is_stale_processing

        rows = await self.plan_repo.list(self.session)
        now = utcnow()
        count = 0
        for row in rows:
            if row.status == "processing" and is_stale_processing(row.updated_at, now, timeout_seconds):
                await self.plan_repo.mark_status(self.session, row.id, "failed")
                count += 1
        return count

    async def create(self, content_id: str, trigger: str = "manual") -> dict:
        """获取一篇笔记的方案；已生成则直接返回，否则强制生成后返回。"""
        logger.info("获取方案 content_id=%s trigger=%s", content_id, trigger)
        row = await self.plan_repo.get_by_content_id(self.session, content_id)
        # 已完成或正在生成中：直接返回，不再重复起任务
        if row is not None and row.status in ("done", "processing"):
            return {**to_dict(row), "_regenerated": False}

        await self.schedule_generation(content_id, force=True)
        row = await self.plan_repo.get_by_content_id(self.session, content_id)
        if row is None:
            raise ValueError("方案生成失败")
        return {**to_dict(row), "_regenerated": True}

    async def regenerate_with_feedback(self, content_id: str, feedback: str) -> dict:
        """按操作者的人工修改要求重写文案（渠道保持不变）。"""
        feedback = (feedback or "").strip()
        if not feedback:
            raise ValueError("请填写修改要求")

        row = await self.plan_repo.get_by_content_id(self.session, content_id)
        if row is None:
            raise ValueError("方案不存在，请先生成方案")

        # 原方案没有文案（skipped/无渠道）：走完整生成流程
        if row.channel not in ("dm", "public"):
            await self._do_generation(content_id, force=True)
        else:
            await self._rewrite_draft(content_id, row.channel, feedback)

        row = await self.plan_repo.get_by_content_id(self.session, content_id)
        if row is None:
            raise ValueError("重新生成失败")
        return to_dict(row)

    async def _rewrite_draft(self, content_id: str, channel: str, human_feedback: str) -> None:
        """渠道不变，只重写文案：复用文案节点 + 打分回环，最多 2 轮。"""
        from .workflows.planning_workflow import _draft_node, _score_node

        analysis = await self.analysis_repo.latest_for_content(self.session, content_id)
        note = await self.content_repo.get_by_external_id(self.session, content_id)
        state: dict = {
            "content_id": content_id,
            "channel": channel,
            "title": note.title if note else "",
            "body": note.body if note else "",
            "sentiment": analysis.sentiment if analysis else "",
            "risk_level": analysis.risk_level if analysis else "",
            "risk_reason": analysis.summary if analysis else "",
            "human_feedback": human_feedback,
            "feedback": "",
            "rounds": 0,
            "dimensions": await _load_dimensions(self.session, content_id),
        }

        # 写文案 → 打分，不达标最多重写 2 轮
        for _ in range(2):
            state.update(await _draft_node(state))
            state.update(await _score_node(state))
            if state.get("passed"):
                break

        # 覆盖到数据库：渠道/原因不变，只替换文案
        plan_row = await self.plan_repo.get_by_content_id(self.session, content_id)
        if plan_row is None:
            return None
        text = state.get("draft_text", "")
        if channel == "dm":
            plan_row.dm_copy = text
            plan_row.comment_copy = ""
        else:
            plan_row.comment_copy = text
            plan_row.dm_copy = ""
        plan_row.status = "done"
        await self.session.flush()
        return None

    async def decide(self, plan_id: uuid.UUID, status: str, decided_by: str = "") -> dict:
        """对方案做决策：采纳(accepted)或关闭(closed)。"""
        if status not in ("accepted", "closed"):
            raise ValueError("决策只能是 accepted(采纳) 或 closed(关闭)")
        row = await self.plan_repo.get(self.session, plan_id)
        if row is None:
            raise ValueError("方案不存在")
        row.status = status
        row.decided_at = utcnow()
        row.decided_by = decided_by
        await self.session.flush()
        return to_dict(row)

    async def complete(self, content_id: str, decided_by: str = "") -> dict:
        """把一篇笔记标记为已处理（closed），移入"处理记录"。

        两类笔记都会走到这里：已生成方案的正常关闭；正面/低风险的"无需处理"关闭。
        若后台任务还没落库导致没有方案记录，这里补一条 skip 方案再关闭。
        """
        row = await self.plan_repo.get_by_content_id(self.session, content_id)
        if row is None:
            brand = await self.brands.get_default(self.session)
            row = await self.plan_repo.upsert(
                self.session, brand.id, content_id, "auto",
                {"channel": "skip", "summary": "无需处理"},
            )
        # 方案还在生成中时不允许关闭，避免把半成品当处理完
        if row.status == "processing":
            raise ValueError("方案正在生成中，请稍后再处理")

        row.status = "closed"
        row.decided_at = utcnow()
        row.decided_by = decided_by
        if row.channel not in ("dm", "public"):
            row.channel = "skip"
        await self.session.flush()

        # 完成处理时，把采用的文案异步写入话术库（失败静默）
        await self._index_copy_after_complete(content_id)
        logger.info("完成处理落库 content_id=%s channel=%s", content_id, row.channel)
        return to_dict(row)

    async def list(self, content_id: str | None = None) -> list[dict]:
        """列出方案；可传笔记 ID 只看某一篇。"""
        rows = await self.plan_repo.list(self.session, content_id)
        return [to_dict(row) for row in rows]

    async def _index_copy_after_complete(self, content_id: str) -> None:
        """完成处理后，把采用的文案写入话术库（失败静默，不阻断主流程）。"""
        try:
            from .plan_copy_index import build_plan_copy_record, schedule_index

            record = await build_plan_copy_record(self.session, content_id)
            if record is not None:
                schedule_index(record)
                logger.info("文案已调度入库 content_id=%s", content_id)
            else:
                logger.info("无可入库文案 content_id=%s", content_id)
        except Exception as exc:
            logger.warning("文案入库构建失败 content_id=%s：%s", content_id, exc)
