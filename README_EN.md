# BitBrowser Automation System

![License](https://img.shields.io/badge/license-MIT-blue.svg) ![Python](https://img.shields.io/badge/python-3.12-blue.svg)

English | **[中文](./README.md)**

---

A **FastAPI + Vue 3 + Playwright/BitBrowser API** automation system for batch Google account operations: account management, window management, 2FA setup/reset, eligibility verification, age verification, and card subscription binding.

This repository is a secondary development of **https://github.com/Leclee/auto_bitbrowser**.

The system uses **BitBrowser** fingerprint browser and controls it via the local API (default `127.0.0.1:54345`).

## 📌 Project Note

- This is just a for-fun fork of someone else's project. I don't run many accounts and I'm not a seller.
- The main goal is automated card binding and age verification.
- The project has many bugs and won't be maintained; it's just a hobby project.

---

## 🎯 Background & Goals

My main goal is to improve this system: I bought many email accounts **without 2FA** to save money, but this caused a lot of trouble (need to batch setup 2FA).

Additionally, I added **age verification** because I found that many accounts gain student eligibility after completing age verification, enabling batch processing of subsequent workflows.

Currently supported features:

* Auto 2FA setup
* Auto 2FA reset
* Auto eligibility verification (student status)
* Auto card binding & subscription
* Age verification (using virtual cards)

---

## ✨ Features

* **Web Management UI**: Account management, search/filter, batch import/export, real-time logs & progress.
* **Browser Window Management**: Create, restore, sync, open/close windows.
* **Task Orchestration**: Execute tasks in order with configurable concurrency and real-time progress updates.
* **2FA Automation**: Auto setup/reset 2FA and sync keys to browser config.
* **Eligibility Verification**: Auto extract SheerID links and verify eligibility, detect account status.
* **Age Verification**: Complete age verification using virtual cards.
* **Card Binding**: Handle multi-layer iframes to complete card binding and subscription.
* **Multi-language Support**: Auto switch account language to English to reduce failures.
* **Unified Data**: SQLite as single data source, auto sync historical text files.

## 🛠️ Installation & Usage

### Requirements

- **Python**: 3.11+ (recommended 3.12)
- **Node.js**: 18+
- **uv**: Python environment manager
- **BitBrowser**: Installed locally with API accessible (default `127.0.0.1:54345`)

### Environment Setup

```bash
# 1) Install dependency tools
pip install uv

# 2) Create and sync Python dependencies (creates .venv)
uv sync

# 3) Install frontend dependencies
cd web/frontend
npm install
```

### Option 1: Quick Start Web UI (Recommended)

```bash
./start_web.sh
```

After startup, access:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Option 2: Manual Start

```bash
# Backend
uv run python -m uvicorn web.backend.main:app --reload --port 8000

# Frontend
cd web/frontend
npm run dev
```

## ⚙️ Configuration

> **🔒 Security Note**: The following config files contain sensitive information (passwords, 2FA keys, card numbers). Please ensure:
> 1. **Do not commit to Git**: These files are already in `.gitignore`
> 2. **Keep safe**: Recommend encrypted storage or password manager
> 3. **Regular backup**: Avoid data loss
> 4. **Use example files**: Refer to `accounts_example.txt` to create your own config

> **Web Config**: You can fill in SheerID API Key and virtual card info in the Web UI "Config" page. The system will prioritize database config; only falls back to `cards.txt` if not configured.

### 1. `accounts.txt` (Account Info)

**📌 Separator Configuration**

Configure separator on the **first line** (uncomment one):

```text
# Separator config (uncomment one line)
分隔符="----"
# 分隔符="---"
# 分隔符="|"
# 分隔符=","
```

**📋 Account Format**

Format (fixed field order): `Email[Separator]Password[Separator]BackupEmail[Separator]2FASecret`

```text
# Standard format (using ---- separator)
分隔符="----"
example1@gmail.com----MyPassword123----backup1@email.com----ABCD1234EFGH5678
example2@gmail.com----P@ssw0rd!%%99----backup2@email.com----WXYZ9012STUV3456

# Email and password only (backup email and 2FA are optional)
example3@gmail.com----ComplexP@ss#2024
```

### 2. `proxies.txt` (Proxy IPs)

Supports Socks5/HTTP, one per line:

```text
socks5://user:pass@host:port
http://user:pass@host:port
```

### 3. `cards.txt` (Virtual Card Info)

Format: `CardNumber Month Year CVV` (space separated)

```text
5481087170529907 01 32 536
5481087143137903 01 32 749
```

💳 **Virtual Card Recommendation**: [HolyCard](https://www.holy-card.com/) - Supports Gemini subscription, GPT Team, $0 Plus

### 4. Output Files (Auto Generated)

* **accounts.db**: SQLite database file
* **sheerIDlink.txt**: Successfully extracted verification links
* **已验证未绑卡.txt**: Accounts verified but not yet bound with card
* **已绑卡号.txt**: Accounts with completed card binding
* **无资格号.txt**: Accounts detected as ineligible

## 📚 Documentation

See [docs/](./docs/) directory for complete technical documentation:

- [Quick Start](./docs/en/quickstart.md)
- [Architecture](./docs/en/architecture.md)
- [Configuration Guide](./docs/en/configuration.md)
- [Task System](./docs/en/task-system.md)
- [Browser Management](./docs/en/browser-management.md)
- [Database Design](./docs/en/database.md)

## ☕ Sponsor

<p align="center">
  <img src="zhanzhu_wx.jpg" alt="WeChat" width="300" />
  <img src="zhanzhu_zfb.jpg" alt="Alipay" width="300" />
</p>

---

## ⚠️ Disclaimer

* This tool is for learning and technical exchange only. Do not use for illegal purposes.
* Please comply with BitBrowser and related platform terms of service.
* The developer is not responsible for any account loss or legal liability arising from the use of this tool.

## 📄 License

This project is licensed under the [MIT License](LICENSE).
