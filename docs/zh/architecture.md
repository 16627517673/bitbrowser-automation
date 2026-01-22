# 系统架构设计

## 概览

Auto BitBrowser 采用前后端分离架构，通过 WebSocket 实现实时通信，使用 Playwright 与 BitBrowser API 进行浏览器自动化控制。

## 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        用户界面层                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Vue 3 前端 (http://localhost:5173)                   │   │
│  │  - 账号管理页面 (AccountsView)                         │   │
│  │  - 浏览器管理页面 (BrowsersView)                       │   │
│  │  - 任务执行页面 (TasksView)                           │   │
│  │  - WebSocket 实时通信                                  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↕ HTTP/WebSocket
┌─────────────────────────────────────────────────────────────┐
│                        应用服务层                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  FastAPI 后端 (http://localhost:8000)                 │   │
│  │  ┌────────────┬────────────┬────────────┬──────────┐ │   │
│  │  │ Accounts   │ Browsers   │ Tasks      │ Config   │ │   │
│  │  │ Router     │ Router     │ Router     │ Router   │ │   │
│  │  └────────────┴────────────┴────────────┴──────────┘ │   │
│  │  ┌──────────────────────────────────────────────────┐ │   │
│  │  │  WebSocket Manager (实时进度推送)                  │ │   │
│  │  └──────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                        数据持久层                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  SQLite 数据库 (accounts.db)                           │   │
│  │  - accounts 表 (账号信息)                              │   │
│  │  - config 表 (配置信息)                                │   │
│  │  DBManager (线程安全的数据库管理器)                     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                        自动化执行层                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Playwright 自动化脚本                                  │   │
│  │  ┌────────────┬────────────┬────────────┬──────────┐ │   │
│  │  │ setup_2fa  │ reset_2fa  │ age_       │ auto_    │ │   │
│  │  │            │            │ verification│ bind_card│ │   │
│  │  └────────────┴────────────┴────────────┴──────────┘ │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                        浏览器控制层                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  BitBrowser API (http://127.0.0.1:54345)              │   │
│  │  - 创建/更新窗口 (POST /browser/update)                │   │
│  │  - 打开窗口 (POST /browser/open)                       │   │
│  │  - 关闭窗口 (POST /browser/close)                      │   │
│  │  - 删除窗口 (POST /browser/delete)                     │   │
│  │  - 获取窗口列表 (POST /browser/list)                   │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                        浏览器实例                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Chromium 浏览器窗口 (指纹隔离)                         │   │
│  │  - 独立 Cookie/LocalStorage                           │   │
│  │  - 独立指纹配置                                         │   │
│  │  - 代理 IP 绑定                                         │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## 核心组件

### 1. 前端 (Vue 3)

**技术栈**:
- Vue 3 (Composition API)
- Vite (构建工具)
- Tailwind CSS (样式框架)
- Axios (HTTP 客户端)

**主要页面**:
- `AccountsView.vue`: 账号管理，支持导入、搜索、筛选、导出
- `BrowsersView.vue`: 浏览器窗口管理，创建、恢复、同步窗口
- `TasksView.vue`: 任务执行，选择账号、配置任务、查看进度

**状态管理**:
- `websocket.js`: WebSocket 连接管理，实时接收任务进度和日志

### 2. 后端 (FastAPI)

**技术栈**:
- FastAPI (Web 框架)
- Uvicorn (ASGI 服务器)
- Pydantic (数据验证)
- asyncio (异步任务)

**路由模块**:
- `accounts.py`: 账号 CRUD、导入导出、状态更新
- `browsers.py`: 浏览器窗口管理、2FA 同步
- `tasks.py`: 任务创建、执行、进度管理
- `config.py`: 配置管理 (SheerID API Key、卡信息)

**WebSocket**:
- `websocket.py`: 实时推送任务进度、日志、账号状态

### 3. 数据层 (SQLite)

**数据库管理器** (`database.py`):
- `DBManager`: 线程安全的数据库操作类
- 自动创建表结构
- 支持从文本文件导入数据

**表结构**:
- `accounts`: 账号信息 (email, password, backup_email, fa_secret, browser_id, status, sheer_link)
- `config`: 配置信息 (key-value 存储)

### 4. 自动化层 (Playwright)

**核心脚本**:
- `setup_2fa.py`: 首次设置 2FA，生成密钥并保存
- `reset_2fa.py`: 修改现有 2FA 密钥
- `age_verification.py`: 使用虚拟卡完成年龄验证
- `run_playwright_google.py`: 获取 SheerID 验证链接
- `auto_bind_card.py`: 自动绑卡订阅

**浏览器控制**:
- `bit_api.py`: BitBrowser REST API 封装
- `create_window.py`: 窗口创建、删除、克隆
- `browser_manager.py`: 浏览器配置持久化

### 5. 外部服务

**BitBrowser API**:
- 本地服务: `http://127.0.0.1:54345`
- 功能: 创建指纹隔离的浏览器窗口
- 重要: 所有请求必须禁用代理 (`proxies={'http': None, 'https': None}`)

**SheerID 验证服务**:
- 服务地址: `https://batch.1key.me`
- 功能: 批量验证学生资格
- 需要: 用户自行配置 API Key

## 数据流

### 任务执行流程

```
1. 用户在前端选择账号和任务类型
   ↓
2. 前端发送 POST /tasks 请求到后端
   ↓
3. 后端创建任务，返回 task_id
   ↓
4. 后端启动异步任务执行器
   ↓
5. 按并发数分批处理账号
   ↓
6. 对每个账号:
   a. 从数据库读取账号信息
   b. 调用 BitBrowser API 打开窗口
   c. 通过 CDP 连接 Playwright
   d. 执行自动化脚本
   e. 更新账号状态到数据库
   f. 通过 WebSocket 推送进度
   ↓
7. 所有账号处理完成，任务结束
   ↓
8. 前端显示最终结果
```

### WebSocket 消息格式

**进度更新**:
```json
{
  "type": "progress",
  "data": {
    "task_id": "xxx",
    "status": "running",
    "completed": 5,
    "total": 10,
    "message": "正在处理..."
  }
}
```

**账号进度**:
```json
{
  "type": "account_progress",
  "data": {
    "email": "user@gmail.com",
    "status": "running",
    "currentTask": "设置 2FA",
    "message": "正在生成密钥..."
  }
}
```

**日志消息**:
```json
{
  "type": "log",
  "data": {
    "time": "12:34:56",
    "level": "info",
    "email": "user@gmail.com",
    "message": "2FA 设置成功"
  }
}
```

## 并发控制

### 任务并发

使用 `asyncio.Semaphore` 控制同时运行的浏览器数量：

```python
semaphore = asyncio.Semaphore(concurrency)  # 默认 1

async with semaphore:
    # 执行任务
    await process_account(account)
```

### 数据库并发

使用线程锁保护数据库操作：

```python
with DBManager.get_db() as conn:
    # 数据库操作
    cursor.execute(...)
```

## 错误处理

### 分层错误处理

1. **自动化脚本层**: 捕获 Playwright 异常，返回 `(success, message)` 元组
2. **任务执行层**: 捕获脚本异常，更新账号状态为 `error`
3. **API 层**: 捕获所有异常，返回标准错误响应
4. **前端层**: 显示错误提示，记录到日志

### 重试机制

- **按钮点击**: 多种选择器尝试，支持 `force=True` 和 `dispatchEvent`
- **元素等待**: 使用 `wait_for_selector` 和 `is_visible()` 检查
- **网络请求**: BitBrowser API 调用失败时记录日志

## 安全设计

### 敏感信息保护

1. **配置文件**: 通过 `.gitignore` 排除敏感文件
2. **数据库**: 本地 SQLite，不上传到版本控制
3. **API Key**: 用户自行配置，无默认值
4. **密码**: 存储在本地数据库，不通过网络传输

### 访问控制

- 后端 API: 仅监听 `localhost`，不对外暴露
- BitBrowser API: 本地服务，无需认证
- WebSocket: 同源策略保护

## 扩展性

### 添加新任务类型

1. 在 `automation-scripts/` 创建新脚本
2. 在 `tasks.py` 添加任务处理函数
3. 在前端 `TasksView.vue` 添加任务选项
4. 更新 `schemas.py` 添加任务类型枚举

### 添加新配置项

1. 在 `config.py` 添加配置键
2. 在 `schemas.py` 更新 `ConfigUpdate` 和 `ConfigResponse`
3. 在前端配置面板添加输入框

## 性能优化

### 前端优化

- 虚拟滚动: 大量账号列表使用虚拟滚动
- 防抖: 搜索输入使用防抖
- 懒加载: 路由懒加载

### 后端优化

- 异步处理: 使用 `asyncio` 并发执行任务
- 数据库索引: 在 `email` 字段创建索引
- WebSocket 批量推送: 合并多条日志消息

### 浏览器优化

- 窗口复用: 任务完成后可选择保持窗口打开
- 并发控制: 限制同时打开的浏览器数量
- 资源清理: 任务结束后关闭不需要的窗口

## 部署建议

### 开发环境

```bash
# 后端
cd web/backend
uvicorn main:app --reload --port 8000

# 前端
cd web/frontend
npm run dev
```

### 生产环境

```bash
# 后端 (使用 gunicorn + uvicorn workers)
gunicorn web.backend.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# 前端 (构建静态文件)
cd web/frontend
npm run build
# 使用 nginx 或其他静态服务器托管 dist/
```

### Docker 部署

```dockerfile
# 示例 Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install uv && uv sync
RUN cd web/frontend && npm install && npm run build

CMD ["uvicorn", "web.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 监控与日志

### 日志级别

- `INFO`: 正常操作日志
- `WARNING`: 可恢复的错误
- `ERROR`: 严重错误

### 日志输出

- 控制台: 开发环境实时查看
- WebSocket: 前端实时显示
- 文件: 可选配置日志文件输出

## 技术债务

### 已知限制

1. **单机部署**: 目前仅支持单机运行，不支持分布式
2. **数据库**: SQLite 不适合高并发场景
3. **认证**: 无用户认证系统，仅本地使用

### 未来改进

1. 支持 PostgreSQL/MySQL
2. 添加用户认证与权限管理
3. 支持分布式任务队列 (Celery/RQ)
4. 添加任务调度功能 (定时任务)
