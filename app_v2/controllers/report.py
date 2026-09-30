"""报表导出接口。

前端"导出报表"按钮调用的接口：把当前统计数据整理成文件（Markdown 或 Excel）给用户下载。
"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..services.report_service import ReportService

router = APIRouter()


@router.get("/reports/export")
async def export_report(format: str = Query(default="markdown"), session: AsyncSession = Depends(get_session)):
    """导出一份舆情分析报告（markdown 或 xlsx）。"""
    if format not in ("markdown", "xlsx"):
        raise HTTPException(status_code=400, detail="format 只能是 markdown 或 xlsx")
    service = ReportService(session)
    if format == "markdown":
        content, media_type, filename = await service.build_markdown()
    else:
        content, media_type, filename = await service.build_xlsx()
    # 通过响应头让浏览器自动开始下载
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )
