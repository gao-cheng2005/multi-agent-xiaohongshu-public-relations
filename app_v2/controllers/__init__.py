"""
controllers 接口层入口。

网页请求到达后，会先经过这里登记的路由（router），
再被分发给对应的业务处理函数。

这里把各个功能模块的小路由都合并到同一个大路由上，
统一加上 /api/v1 前缀，方便前端统一调用。
"""
from fastapi import APIRouter

from . import alert, analytics, collect, config, content, health, keyword, llm, plan, report

# 创建一个总路由，给所有接口统一加 /api/v1 前缀
router = APIRouter(prefix="/api/v1")

# 把每个功能模块的小路由都挂到总路由下
for module in (health, keyword, config, collect, content, alert, plan, analytics, report, llm):
    router.include_router(module.router)