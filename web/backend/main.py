"""
FastAPI 后端入口
Web UI 管理系统
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import DBManager
from .routers import accounts, browsers, tasks, config
from .websocket import router as ws_router

# 初始化数据库
DBManager.init_db()

app = FastAPI(
    title="Auto BitBrowser 管理系统",
    description="账号管理、浏览器窗口管理、自动化任务执行",
    version="1.0.0",
)

# CORS 配置（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(accounts.router, prefix="/api/accounts", tags=["账号管理"])
app.include_router(browsers.router, prefix="/api/browsers", tags=["浏览器管理"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["任务执行"])
app.include_router(config.router, prefix="/api/config", tags=["配置管理"])
app.include_router(ws_router, tags=["WebSocket"])


@app.get("/")
async def root():
    return {"message": "Auto BitBrowser 管理系统 API", "version": "1.0.0"}


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
