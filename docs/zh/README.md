# Auto BitBrowser 项目文档

[English](../en/README.md) | **中文**

---

欢迎查阅 Auto BitBrowser 自动化管理系统的技术文档。

## 📚 文档目录

### 基础文档
- [快速开始](./quickstart.md) - 安装配置与快速上手
- [配置指南](./configuration.md) - 详细配置说明

### 核心模块
- [架构设计](./architecture.md) - 系统架构与技术栈
- [数据库设计](./database.md) - 数据模型与表结构
- [任务系统](./task-system.md) - 任务编排与执行流程
- [浏览器管理](./browser-management.md) - BitBrowser API 集成

## 🎯 项目概述

Auto BitBrowser 是一个基于 **FastAPI + Vue 3 + Playwright** 的自动化管理系统，专为 Google 账号批处理场景设计。

### 核心功能
- 账号与浏览器窗口管理
- 2FA 自动化设置与修改
- 年龄验证与资格检测
- 绑卡订阅自动化
- 实时任务进度与日志

### 技术栈
- **后端**: Python 3.11+, FastAPI, SQLite
- **前端**: Vue 3, Vite, Tailwind CSS
- **自动化**: Playwright, BitBrowser API
- **通信**: WebSocket (实时推送)

## 🚀 快速导航

### 我想...
- **了解系统架构** → [架构设计](./architecture.md)
- **开始使用** → [快速开始](./quickstart.md)
- **配置账号和卡片** → [配置指南](./configuration.md)
- **理解任务执行流程** → [任务系统](./task-system.md)
- **管理浏览器窗口** → [浏览器管理](./browser-management.md)
- **查看数据库结构** → [数据库设计](./database.md)

## 📞 获取帮助

- **GitHub Issues**: 报告 Bug 或提出功能建议
- **文档反馈**: 如果文档有不清楚的地方，欢迎提 Issue

## 📄 许可证

本项目采用 MIT 许可证。详见 [LICENSE](../../LICENSE) 文件。
