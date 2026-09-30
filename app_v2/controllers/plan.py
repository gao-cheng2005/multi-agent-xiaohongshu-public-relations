"""应对方案接口。

前端生成、查看、处理应对方案调用的接口都在这里：查看方案列表、为某篇笔记生成方案、
对方案做决策（采纳或关闭）、完成处理、按修改要求重新生成。
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import SessionLocal, get_session
from ..services.plan_service import PlanService

router = APIRouter()


async def _run_generation_async(content_id: str) -> None:
    """在独立数据库会话里异步跑方案生成，避免占用请求会话。"""
    try:
        async with SessionLocal() as session:
            await PlanService(session).schedule_generation(content_id)
            await session.commit()
    except Exception:
        pass


@router.post("/plans/complete")
async def complete_plan(payload: dict, session: AsyncSession = Depends(get_session)):
    """把一篇笔记标记为已处理（closed），移入"处理记录"。"""
    content_id = (payload or {}).get("content_id")
    if not content_id:
        raise HTTPException(status_code=400, detail="请提供 content_id")
    decided_by = (payload or {}).get("decided_by", "")
    try:
        return await PlanService(session).complete(content_id, decided_by)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/plans/regenerate")
async def regenerate_plan(payload: dict, session: AsyncSession = Depends(get_session)):
    """按操作者的人工修改要求重新生成文案（渠道不变，覆盖原文案）。"""
    content_id = (payload or {}).get("content_id")
    feedback = (payload or {}).get("feedback", "")
    if not content_id:
        raise HTTPException(status_code=400, detail="请提供 content_id")
    try:
        return await PlanService(session).regenerate_with_feedback(content_id, feedback)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/plans/generate")
async def generate_plan(payload: dict, session: AsyncSession = Depends(get_session)):
    """手动触发方案生成（异步执行，返回后前端轮询状态）。"""
    content_id = (payload or {}).get("content_id")
    if not content_id:
        raise HTTPException(status_code=400, detail="请提供 content_id")
    asyncio.get_running_loop().create_task(_run_generation_async(content_id))
    return {"ok": True}


@router.get("/plans")
async def get_plans(
    content_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """获取方案列表；可传笔记 ID 只看那一篇。"""
    return await PlanService(session).list(content_id)


@router.post("/plans")
async def make_plan(payload: dict, session: AsyncSession = Depends(get_session)):
    """为某篇笔记生成应对方案（trigger 为 auto 或 manual）。"""
    content_id = (payload or {}).get("content_id")
    trigger = (payload or {}).get("trigger", "manual")
    if not content_id:
        raise HTTPException(status_code=400, detail="请提供 content_id")
    try:
        return await PlanService(session).create(content_id, trigger=trigger)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/plans/{plan_id}/decide")
async def decide_plan(
    plan_id: uuid.UUID,
    payload: dict,
    session: AsyncSession = Depends(get_session),
):
    """对方案做决策：采纳(accepted)或关闭(closed)。"""
    status = (payload or {}).get("status", "closed")
    decided_by = (payload or {}).get("decided_by", "")
    try:
        return await PlanService(session).decide(plan_id, status, decided_by)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
