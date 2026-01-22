# Auto BitBrowser Web UI

基于 FastAPI + Vue 3 的现代化 Web 管理界面。

## 功能

- **账号管理**: 列表、搜索、筛选、批量导入/导出
- **浏览器窗口管理**: 创建、删除、恢复、同步
- **任务执行**: 批量执行自动化任务，实时进度推送
- **WebSocket 实时通信**: 任务进度和日志实时更新

## 技术栈

- **后端**: FastAPI + SQLite
- **前端**: Vue 3 + Vite + TailwindCSS + Pinia
- **实时通信**: WebSocket

## 快速启动

### 1. 安装后端依赖

```bash
pip install fastapi uvicorn websockets
```

### 2. 安装前端依赖

```bash
cd web/frontend
npm install
```

### 3. 启动服务

**方式一：使用启动脚本**

```bash
# 终端 1 - 启动后端
./web/start_backend.sh

# 终端 2 - 启动前端
./web/start_frontend.sh
```

**方式二：手动启动**

```bash
# 终端 1 - 启动后端 (在项目根目录)
uvicorn web.backend.main:app --reload --port 8000

# 终端 2 - 启动前端
cd web/frontend
npm run dev
```

### 4. 访问

- 前端: http://localhost:5173
- 后端 API: http://localhost:8000
- API 文档: http://localhost:8000/docs

## 目录结构

```
web/
├── backend/                 # FastAPI 后端
│   ├── main.py             # 应用入口
│   ├── schemas.py          # Pydantic 数据模型
│   ├── websocket.py        # WebSocket 管理
│   └── routers/            # API 路由
│       ├── accounts.py     # 账号管理 API
│       ├── browsers.py     # 浏览器管理 API
│       └── tasks.py        # 任务执行 API
│
├── frontend/               # Vue 3 前端
│   ├── src/
│   │   ├── api/           # API 调用封装
│   │   ├── stores/        # Pinia 状态管理
│   │   ├── views/         # 页面组件
│   │   ├── App.vue        # 主组件
│   │   ├── main.js        # 入口文件
│   │   └── router.js      # 路由配置
│   ├── package.json
│   └── vite.config.js
│
├── start_backend.sh        # 后端启动脚本
├── start_frontend.sh       # 前端启动脚本
└── README.md              # 本文件
```

## API 端点

### 账号管理 `/api/accounts`

- `GET /` - 获取账号列表（支持分页、搜索、筛选）
- `GET /stats` - 获取统计信息
- `GET /{email}` - 获取账号详情
- `POST /` - 创建账号
- `PUT /{email}` - 更新账号
- `DELETE /{email}` - 删除账号
- `POST /import` - 批量导入
- `GET /export/all` - 导出账号

### 浏览器管理 `/api/browsers`

- `GET /` - 获取浏览器列表
- `GET /sync` - 同步到数据库
- `GET /{id}` - 获取浏览器详情
- `POST /` - 创建浏览器窗口
- `DELETE /{id}` - 删除浏览器窗口
- `POST /{id}/open` - 打开浏览器
- `POST /restore/{email}` - 恢复浏览器窗口

### 任务执行 `/api/tasks`

- `GET /` - 获取任务列表
- `GET /{id}` - 获取任务状态
- `POST /` - 创建并执行任务
- `DELETE /{id}` - 取消任务

### WebSocket `/ws`

连接后可接收实时消息：
- `task_progress` - 任务进度更新
- `log` - 日志消息

## 注意事项

1. 确保比特浏览器已启动且 API 可访问（默认 127.0.0.1:54345）
2. 首次运行会自动从 accounts.txt 导入账号到数据库
3. 任务执行使用后台线程，不会阻塞 API
