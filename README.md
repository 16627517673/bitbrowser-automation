# BitBrowser Automation System

![License](https://img.shields.io/badge/license-MIT-blue.svg) ![Python](https://img.shields.io/badge/python-3.12-blue.svg)

**[English](./README_EN.md)** | 中文

---

这是一个基于 **FastAPI + Vue 3 + Playwright/BitBrowser API** 的自动化管理系统，面向 Google 账号批处理场景，支持账号管理、窗口管理、2FA 设置/修改、资格验证、年龄验证与绑卡订阅等任务。

本项目为对 **https://github.com/Leclee/auto_bitbrowser** 的二次开发版本。

系统使用 **BitBrowser 指纹浏览器**，通过本地 API（默认 `127.0.0.1:54345`）进行窗口与指纹配置控制。

使用教程文档：https://docs.qq.com/doc/DSEVnZHprV0xMR05j?no_promotion=1&is_blank_or_template=blank

## 📌 项目说明

- 只是看到别人的项目做着玩玩，没有弄很多号，也不是号商。
- 主要想做自动绑卡与年龄验证。
- 项目有很多 bug，后续也不会维护，开发者只是玩玩。

---

## 🎯 使用背景与目标

我的主要目标是完善这个系统：为了省钱购买了大量**没有 2FA** 的邮箱账号，但这带来了很大麻烦（需要批量设置 2FA）。

此外，之所以加入**年龄验证**，是因为我发现很多账号在完成年龄验证后就拥有了学生资格，从而可以批量处理后续流程。

目前系统已支持：

* 自动设置 2FA
* 自动修改 2FA
* 自动资格验证（学生资格）
* 自动绑卡订阅
* 年龄验证（使用虚拟卡验证）

---

## ✨ 功能特性

* **Web 管理界面**：账号管理、筛选搜索、批量导入/导出、实时日志与进度展示。
* **浏览器窗口管理**：创建、恢复、同步、打开/关闭窗口。
* **任务编排与并发**：按账号顺序执行任务，支持并发数配置与实时进度推送。
* **2FA 自动化**：自动设置 2FA、修改 2FA，并将密钥同步到指纹浏览器配置。
* **资格验证**：自动获取 SheerID 链接并完成资格验证，识别账号状态。
* **年龄验证**：使用虚拟卡完成年龄验证，提升学生资格覆盖率。
* **绑卡订阅**：自动处理多层 iframe，完成绑卡与订阅流程。
* **多语言适配**：自动切换账号语言为英文，减少多语言导致的操作失败。
* **数据统一**：SQLite 为单一数据源，自动同步历史文本文件。

## 🛠️ 安装与使用

### 环境准备

- **Python**: 3.11+（推荐 3.12）
- **Node.js**: 18+
- **uv**: Python 环境管理工具（用于一键创建虚拟环境并安装依赖）
- **BitBrowser**: 本地已安装并可访问 API（默认 `127.0.0.1:54345`）

### 项目环境配置

```bash
# 1) 安装依赖工具（示例）
pip install uv

# 2) 创建并同步 Python 依赖（会生成 .venv）
uv sync

# 3) 安装前端依赖
cd web/frontend
npm install
```

### 方式一：一键启动 Web UI (推荐)

```bash
./start_web.sh
```

启动后访问：
- 前端: http://localhost:5173
- 后端 API: http://localhost:8000
- API 文档: http://localhost:8000/docs

### 方式二：手动启动

```bash
# 后端
uv run python -m uvicorn web.backend.main:app --reload --port 8000

# 前端
cd web/frontend
npm run dev
```

## ⚙️ 配置文件说明

> **🔒 安全提示**: 以下配置文件包含敏感信息（账号密码、2FA密钥、卡号等），请确保：
> 1. **不要提交到 Git 仓库**：这些文件已在 `.gitignore` 中配置
> 2. **妥善保管**：建议加密存储或使用密码管理器
> 3. **定期备份**：避免数据丢失
> 4. **使用示例文件**：参考 `accounts_example.txt` 创建自己的配置

> **Web 配置**：在 Web 管理界面的"配置"页可填写 SheerID API Key 与虚拟卡信息，系统会优先使用数据库配置；未配置时才会回退到 `cards.txt`。

### 1. `accounts.txt` (账号信息)

**📌 分隔符配置方式**

在文件**第一行**配置分隔符（取消注释即可）：

```text
# 分隔符配置（取消注释其中一行）
分隔符="----"
# 分隔符="---"
# 分隔符="|"
# 分隔符=","
```

**📋 账号格式说明**

格式（字段顺序固定）：`邮箱[分隔符]密码[分隔符]辅助邮箱[分隔符]2FA密钥`

```text
# 标准格式（使用 ---- 分隔）
分隔符="----"
example1@gmail.com----MyPassword123----backup1@email.com----ABCD1234EFGH5678
example2@gmail.com----P@ssw0rd!%%99----backup2@email.com----WXYZ9012STUV3456

# 只有邮箱和密码（辅助邮箱和2FA可选）
example3@gmail.com----ComplexP@ss#2024
```

### 2. `proxies.txt` (代理IP)

支持 Socks5/HTTP，一行一个：

```text
socks5://user:pass@host:port
http://user:pass@host:port
```

### 3. `cards.txt` (虚拟卡信息)

格式：`卡号 月份 年份 CVV`（空格分隔）

```text
5481087170529907 01 32 536
5481087143137903 01 32 749
```

💳 **虚拟卡推荐**：[HolyCard](https://www.holy-card.com/) - 支持Gemini订阅、GPT Team、0刀Plus

### 4. 输出文件 (程序自动生成)

* **accounts.db**: SQLite 数据库文件
* **sheerIDlink.txt**: 成功提取的验证链接
* **已验证未绑卡.txt**: 已通过学生验证但未绑卡的账号
* **已绑卡号.txt**: 已完成绑卡订阅的账号
* **无资格号.txt**: 检测到无资格的账号

## 📚 详细文档

查看 [docs/](./docs/) 目录获取完整技术文档：

- [快速开始](./docs/zh/quickstart.md)
- [架构设计](./docs/zh/architecture.md)
- [配置指南](./docs/zh/configuration.md)
- [任务系统](./docs/zh/task-system.md)
- [浏览器管理](./docs/zh/browser-management.md)
- [数据库设计](./docs/zh/database.md)

## ☕ 赞助 / Sponsor

<p align="center">
  <img src="zanshang.jpg" alt="微信赞赏" width="300" />
  <img src="QQ.jpg" alt="QQ" width="300" />
</p>

---

## ⚠️ 免责声明

* 本工具仅供学习与技术交流使用，请勿用于非法用途。
* 请遵守比特浏览器及相关平台的使用条款。
* 开发者不对因使用本工具产生的任何账号损失或法律责任负责。

## 📄 License

本项目采用 [MIT License](LICENSE)。
