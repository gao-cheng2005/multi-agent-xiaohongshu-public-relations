"""统计接口。

前端"数据分析"页面和首页卡片调用的接口：整体统计、情感趋势、热词、
总览趋势、方案与预警效果，以及产品维度分析和优化建议报告。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..services.analytics_service import AnalyticsService
from ..services.content_service import ContentService

router = APIRouter()


@router.get("/stats")
async def get_stats(session: AsyncSession = Depends(get_session)):
    """获取整体统计数字（首页卡片用）。"""
    return await ContentService(session).stats()


@router.get("/analytics/trend")
async def analytics_trend(days: int = Query(default=30, ge=1, le=365), session: AsyncSession = Depends(get_session)):
    """近 N 天的情感趋势（默认 30 天）。"""
    return await AnalyticsService(session).trend(days)


@router.get("/analytics/hotwords")
async def analytics_hotwords(limit: int = Query(default=20, ge=1, le=100), session: AsyncSession = Depends(get_session)):
    """出现次数最多的热词（默认前 20）。"""
    return await AnalyticsService(session).hotwords(limit)


@router.get("/analytics/overview_trend")
async def analytics_overview_trend(
    days: int = Query(default=7, ge=1, le=90),
    product: str = Query(default=""),
    session: AsyncSession = Depends(get_session),
):
    """近 N 天每天采集笔记数 + 中高风险笔记数（可按产品过滤）。"""
    return await AnalyticsService(session).overview_trend(days, product)


@router.get("/analytics/effect")
async def analytics_effect(session: AsyncSession = Depends(get_session)):
    """方案与预警的处理效果统计。"""
    return await AnalyticsService(session).effect()


@router.get("/analytics/product")
async def product_analysis(product: str = Query(default=""), session: AsyncSession = Depends(get_session)):
    """单个产品的用户问题分析。"""
    if not product:
        raise HTTPException(status_code=400, detail="请提供产品名")
    return await AnalyticsService(session).product_analysis(product)


@router.get("/analytics/product/report")
async def product_report_get(product: str = Query(default=""), session: AsyncSession = Depends(get_session)):
    """读取产品优化建议缓存。"""
    if not product:
        raise HTTPException(status_code=400, detail="请提供产品名")
    report = await AnalyticsService(session).get_product_report(product)
    return report or {}


@router.post("/analytics/product/report")
async def product_report(payload: dict, session: AsyncSession = Depends(get_session)):
    """手动重新生成产品优化建议（结果自动缓存）。"""
    product = (payload or {}).get("product", "")
    if not product:
        raise HTTPException(status_code=400, detail="请提供产品名")
    return await AnalyticsService(session).generate_product_report(product)


@router.post("/analytics/product/merge")
async def product_merge(payload: dict, session: AsyncSession = Depends(get_session)):
    """归并待确认维度（批量执行）。"""
    product = (payload or {}).get("product", "")
    if not product:
        raise HTTPException(status_code=400, detail="请提供产品名")
    return await AnalyticsService(session).merge_dimensions(product)


@router.post("/analytics/dimension/confirm")
async def dimension_confirm(payload: dict, session: AsyncSession = Depends(get_session)):
    """人工确认（或忽略）一个待确认维度。"""
    product = (payload or {}).get("product", "")
    dimension = (payload or {}).get("dimension", "")
    confirmed = bool((payload or {}).get("confirmed", True))
    if not dimension:
        raise HTTPException(status_code=400, detail="请提供维度名")
    count = await AnalyticsService(session).confirm_dimension(product, dimension, confirmed)
    return {"ok": True, "count": count}
