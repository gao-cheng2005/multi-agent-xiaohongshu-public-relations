"""本地启动入口（V2，开发/部署用）。

职责：用 uvicorn 拉起 FastAPI 应用。
调用了谁：app_v2.main（应用装配模块），监听本机 127.0.0.1:8000。
"""

import uvicorn


if __name__ == "__main__":
    uvicorn.run("app_v2.main:app", host="127.0.0.1", port=8000, reload=False)