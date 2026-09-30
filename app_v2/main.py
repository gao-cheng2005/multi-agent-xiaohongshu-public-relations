"""
main 应用入口（服务器启动的核心文件）。

这里创建了 FastAPI 网页应用的"心脏"：
- 组装应用：注册各个接口路由、允许跨域访问；
- 定义启动流程：服务器启动时先自动升级数据库，再开始对外服务；
- 提供对外服务的应用对象 app，由 uvicorn 运行它。

（FastAPI：一个用 Python 写网页接口（API）的框架，
uvicorn：负责真正把应用跑起来、监听端口接收请求的服务器程序。）
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .controllers import router
from .core.settings import settings
from .db.bootstrap import upgrade_database
from .db.session import SessionLocal
from .services.plan_service import PlanService


@asynccontextmanager
async def lifespan(app: FastAPI):
    """服务器的"生命周期"管理。

    服务器启动时先执行升级数据库（确保表存在），
    然后正式对外服务；关闭时（如有需要）做清理工作。
    """
    # 启动阶段：保证数据库已就绪
    upgrade_database()
    # 恢复用户上次在设置页选择的模型（SystemConfig.llm_model），让 gateway 一致
    try:
        from .core.llm import llm_gateway
        from .services.llm_config_service import LLMConfigService

        async with SessionLocal() as session:
            model = await LLMConfigService(session).get_current_model()
            llm_gateway.set_active_model(model)
    except Exception:
        pass
    # 把上次进程中断留下的"处理中"方案重置为失败，避免前端永远转圈
    try:
        async with SessionLocal() as session:
            await PlanService(session).reset_stale_processing()
    except Exception:
        pass
    yield


# 创建应用对象：给应用起名字、定版本号，并挂上启动流程
app = FastAPI(title=settings.app_name, version="2.0.0", lifespan=lifespan)

# 允许跨域访问（前端在另一个端口/browser 上访问时不会受阻）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 把之前组装好的总路由注册进应用
app.include_router(router)