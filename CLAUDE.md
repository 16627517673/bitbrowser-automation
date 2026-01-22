# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

比特浏览器（BitBrowser）自动化管理工具，用于批量管理 Google 账号的学生验证流程，包括 2FA 设置、年龄验证、SheerID 链接获取和虚拟卡绑定订阅。

## 常用命令

### 后端启动
```bash
cd web/backend && uvicorn main:app --reload --port 8000
```

### 前端启动
```bash
cd web/frontend && npm run dev
```

### GUI 桌面应用
```bash
python create_window_gui.py
```

### 安装依赖
```bash
# Python (使用 uv)
uv sync

# 前端
cd web/frontend && npm install

# Playwright 浏览器
playwright install
```

## 架构概览

### 核心层次

```
├── 数据层
│   └── database.py          # DBManager 类，SQLite 单一数据源 (accounts.db)
│
├── 浏览器控制层
│   ├── bit_api.py           # 比特浏览器 REST API (127.0.0.1:54345)
│   ├── create_window.py     # 窗口创建/删除/克隆
│   └── browser_manager.py   # 浏览器配置持久化与恢复
│
├── 自动化任务层 (Playwright)
│   ├── setup_2fa.py         # 首次设置 2FA
│   ├── reset_2fa.py         # 重置/更新 2FA 密钥
│   ├── age_verification.py  # Google 年龄验证
│   ├── run_playwright_google.py  # 获取 SheerID 验证链接
│   └── auto_bind_card.py    # 虚拟卡绑定订阅
│
├── Web 管理层
│   ├── web/backend/         # FastAPI 后端
│   │   ├── main.py          # 入口，注册路由
│   │   ├── routers/         # API 路由 (accounts, browsers, tasks, config)
│   │   ├── schemas.py       # Pydantic 模型
│   │   └── websocket.py     # 实时进度推送
│   └── web/frontend/        # Vue 3 + Vite 前端
│       └── src/views/       # 页面组件
│
└── GUI 层
    └── create_window_gui.py # PyQt6 桌面界面
```

### 关键数据流

1. **账号数据**: `accounts.txt` → `DBManager.import_from_files()` → `accounts.db`
2. **浏览器窗口**: 比特浏览器 API ↔ `create_window.py` ↔ `browser_manager.py`
3. **任务执行**: Web API → `tasks.py` → 自动化脚本 (Playwright) → WebSocket 进度更新

### 比特浏览器 API

本地服务地址: `http://127.0.0.1:54345`

核心接口:
- `POST /browser/update` - 创建/更新窗口
- `POST /browser/open` - 打开窗口，返回 WebSocket 端点用于 Playwright 连接
- `POST /browser/close` - 关闭窗口
- `POST /browser/delete` - 删除窗口
- `POST /browser/list` - 获取窗口列表

**重要**: 所有 API 请求必须禁用代理 (`proxies={'http': None, 'https': None}`)

## 账号格式

`accounts.txt` 格式: `邮箱----密码----辅助邮箱----2FA密钥`

分隔符支持: `----` (推荐), `---`, `|`, `,`

## 开发注意事项

- Python 要求 ≥3.11，使用静态类型 (Type Hints)
- 数据库操作使用 `DBManager` 类，支持线程安全
- Playwright 通过 CDP 连接比特浏览器: `chromium.connect_over_cdp(ws_endpoint)`
- 任务执行函数统一返回 `(success: bool, message: str)` 或 `(success, message, data)` 元组
