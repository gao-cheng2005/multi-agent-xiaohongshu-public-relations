"""内容接口。

前端"舆情内容"页面调用的接口都在这里：查看笔记列表、查看筛选条件、查看某篇笔记的评论、
按条件删除笔记、获取"打开原文"的链接、查看系统信息。

接口层只负责接收请求、校验参数、调用服务层并返回结果。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..services.content_service import ContentService

router = APIRouter()


@router.delete("/contents")
async def delete_contents(
    content_id: str | None = Query(default=None),
    q: str = Query(default=""),
    source_type: str = Query(default=""),
    keyword: str = Query(default=""),
    sentiment: str = Query(default=""),
    risk: str = Query(default=""),
    channel: str = Query(default=""),
    allow_handled: bool = Query(default=False),
    handled_only: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
):
    """按条件删除笔记并级联清理关联数据，返回删除条数。

    content_id 单条删除；其余为筛选条件；allow_handled 允许删已处理的；
    handled_only 只删已处理的；全部为空 = 删全部。
    """
    count = await ContentService(session).delete_contents(
        content_id=content_id or None,
        q=q or "",
        source_type=source_type or "",
        keyword=keyword or "",
        sentiment=sentiment or "",
        risk=risk or "",
        channel=channel or "",
        allow_handled=allow_handled,
        handled_only=handled_only,
    )
    return {"ok": True, "count": count}


@router.get("/contents/recent-pending")
async def get_recent_pending(
    limit: int = Query(default=5, ge=1, le=20),
    session: AsyncSession = Depends(get_session),
):
    """最近的中高风险未处理笔记，供总览页"最近预警"用。"""
    return await ContentService(session).recent_pending_notes(limit)


@router.get("/contents/processed")
async def get_processed_contents(
    q: str = Query(default=""),
    source_type: str = Query(default=""),
    keyword: str = Query(default=""),
    sentiment: str = Query(default=""),
    risk: str = Query(default=""),
    channel: str = Query(default=""),
    limit: int = Query(default=200, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    """已处理（方案 closed）的笔记列表，支持筛选、按处理时间排序。"""
    return await ContentService(session).list_processed_contents(
        q=q or "",
        source_type=source_type or "",
        keyword=keyword or "",
        sentiment=sentiment or "",
        risk=risk or "",
        channel=channel or "",
        limit=limit,
    )


@router.get("/contents")
async def get_contents(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    """获取笔记列表（默认最近 100 条，最多 500 条）。"""
    return await ContentService(session).list_contents(limit)


@router.get("/contents/filters")
async def get_content_filters(session: AsyncSession = Depends(get_session)):
    """获取筛选条件（来源、关键词），供前端下拉框使用。"""
    return await ContentService(session).content_filters()


@router.get("/contents/{content_id}/comments")
async def get_content_comments(
    content_id: str,
    session: AsyncSession = Depends(get_session),
):
    """获取某篇笔记的评论列表。"""
    return await ContentService(session).list_comments(content_id)


@router.post("/contents/{content_id}/open")
async def open_content(content_id: str, session: AsyncSession = Depends(get_session)):
    """获取一篇笔记"当前可用"的打开链接。

    小红书链接带有时效签名，过期就打不开，所以点击"打开原文"时先来这里拿一条新鲜链接。
    """
    try:
        return {"url": await ContentService(session).refresh_note_url(content_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/info")
async def get_info(session: AsyncSession = Depends(get_session)):
    """获取系统信息（采集方式、大模型配置等），供设置页展示。"""
    return await ContentService(session).info()
