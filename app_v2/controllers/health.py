"""健康检查接口。

给前端（或运维脚本）提供一个简单的"探路桩"：能访问到这个接口，就说明后端服务活着。
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    """返回固定的成功信息，证明服务正常。"""
    return {"status": "ok"}
