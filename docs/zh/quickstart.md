# 快速开始

## 环境要求

### 必需软件

- **Python**: 3.11 或更高版本（推荐 3.12）
- **Node.js**: 18 或更高版本
- **uv**: Python 包管理工具
- **BitBrowser**: 指纹浏览器客户端

### 系统要求

- **操作系统**: Windows 10+, macOS 10.15+, Linux
- **内存**: 最少 8GB（推荐 16GB）
- **磁盘空间**: 至少 5GB 可用空间

## 安装步骤

### 1. 克隆项目

```bash
git clone https://github.com/yourusername/auto_bitbrowser.git
cd auto_bitbrowser
```

### 2. 安装 Python 依赖

使用 `uv` 管理 Python 环境：

```bash
# 安装 uv（如果还没安装）
pip install uv

# 创建虚拟环境并安装依赖
uv sync
```

这会创建 `.venv` 目录并安装所有 Python 依赖。

### 3. 安装 Playwright 浏览器

```bash
# 激活虚拟环境
source .venv/bin/activate  # macOS/Linux
# 或
.venv\Scripts\activate  # Windows

# 安装 Playwright 浏览器
playwright install chromium
```

### 4. 安装前端依赖

```bash
cd web/frontend
npm install
cd ../..
```

### 5. 准备配置文件

创建账号配置文件：

```bash
# 复制示例文件
cp accounts_example.txt accounts.txt
cp cards_example.txt cards.txt

# 编辑配置文件
nano accounts.txt  # 或使用你喜欢的编辑器
```

## 启动服务

### 方式一：一键启动（推荐）

```bash
./start_web.sh
```

这会同时启动后端和前端服务。

### 方式二：手动启动

**启动后端**:
```bash
cd web/backend
uvicorn main:app --reload --port 8000
```

**启动前端**（新终端）:
```bash
cd web/frontend
npm run dev
```

## 访问应用

启动成功后，在浏览器中访问：

- **前端界面**: http://localhost:5173
- **后端 API**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs

## 首次使用

### 1. 导入账号

**方式一：通过文件导入**

编辑 `accounts.txt` 文件：

```text
分隔符="----"
user1@gmail.com----password123----backup1@email.com----ABCD1234EFGH5678
user2@gmail.com----password456----backup2@email.com----WXYZ9012STUV3456
```

然后在前端点击"导入账号"按钮。

**方式二：通过 Web 界面添加**

1. 访问 http://localhost:5173/accounts
2. 点击"添加账号"按钮
3. 填写账号信息
4. 点击"保存"

### 2. 配置 SheerID API Key（可选）

如果需要使用 SheerID 验证功能：

1. 访问 http://localhost:5173/tasks
2. 点击"⚙️ 配置"按钮
3. 填写 SheerID API Key
4. 点击"保存"

### 3. 配置虚拟卡信息（可选）

如果需要使用年龄验证或绑卡功能：

1. 在配置面板中填写卡号、过期日期、CVV、邮编
2. 点击"保存"

### 4. 创建浏览器窗口

1. 访问 http://localhost:5173/browsers
2. 点击"恢复窗口"按钮
3. 系统会为所有账号创建浏览器窗口

### 5. 执行任务

1. 访问 http://localhost:5173/tasks
2. 选择要处理的账号
3. 选择任务类型（设置 2FA、年龄验证等）
4. 设置并发数
5. 点击"开始执行"

## 常见问题

### Q: 启动后端时报错 "ModuleNotFoundError"

**A**: 确保已激活虚拟环境：

```bash
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate  # Windows
```

### Q: 前端无法连接后端

**A**: 检查后端是否正常运行：

```bash
curl http://localhost:8000/accounts
```

如果无响应，检查后端日志。

### Q: BitBrowser API 连接失败

**A**: 确保 BitBrowser 客户端已启动，并且 API 端口为 54345：

```bash
curl http://127.0.0.1:54345/browser/list
```

### Q: Playwright 连接浏览器失败

**A**: 检查浏览器窗口是否已打开：

1. 在 BitBrowser 客户端中查看窗口列表
2. 确保窗口状态为"运行中"
3. 检查 WebSocket 端点是否正确

### Q: 任务执行失败

**A**: 查看实时日志，常见原因：

- 账号密码错误
- 代理配置错误
- 网络连接问题
- 配置信息缺失

## 下一步

- 阅读 [配置指南](./configuration.md) 了解详细配置
- 阅读 [架构设计](./architecture.md) 了解系统架构
- 阅读 [任务系统](./task-system.md) 了解任务执行流程
- 阅读 [浏览器管理](./browser-management.md) 了解窗口管理

## 获取帮助

如果遇到问题：

1. 查看 [调试技巧](./debugging.md)
2. 查看 GitHub Issues
3. 查看后端日志和前端控制台

## 停止服务

### 停止一键启动的服务

按 `Ctrl+C` 停止 `start_web.sh` 脚本。

### 停止手动启动的服务

在每个终端中按 `Ctrl+C`。

## 卸载

```bash
# 删除虚拟环境
rm -rf .venv

# 删除前端依赖
rm -rf web/frontend/node_modules

# 删除数据库（可选）
rm accounts.db

# 删除配置文件（可选）
rm accounts.txt cards.txt
```

## 更新

```bash
# 拉取最新代码
git pull

# 更新 Python 依赖
uv sync

# 更新前端依赖
cd web/frontend
npm install
cd ../..

# 重启服务
./start_web.sh
```
