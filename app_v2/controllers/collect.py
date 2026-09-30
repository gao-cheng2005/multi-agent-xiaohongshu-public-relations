"""采集接口。

前端"手动采集"页面点"开始采集"后调用的接口。
支持两种方式：按关键词搜索采集、按笔记链接采集。
采集比较耗时（要驱动浏览器），所以这里不做超时限制，让前端耐心等待。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..models.schemas import CollectRequest
from ..services.collect_service import CollectService, NoCollectableDataError

router = APIRouter()


@router.post("/collect")
async def trigger_collect(payload: CollectRequest, session: AsyncSession = Depends(get_session)):
    """触发一次采集，返回采集结果（笔记数、评论数、预警数等）。"""
    if not payload.keyword and not payload.note_url:
        raise HTTPException(status_code=400, detail="请提供 keyword 或 note_url")
    try:
        return await CollectService(session).collect(
            keyword=payload.keyword,
            note_url=payload.note_url,
            limit=payload.limit,
            fetch_comments=payload.fetch_comments,
            comment_depth=payload.comment_depth,
        )
    except NoCollectableDataError as exc:
        # 明确表示"确实没采到内容"，返回 422 而不是笼统报错
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        # 采集过程出错（如没装 OpenCLI、链接失效），返回 502
        raise HTTPException(status_code=502, detail=str(exc)) from exc
