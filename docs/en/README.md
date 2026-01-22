# Auto BitBrowser Documentation

English documentation for Auto BitBrowser - an automated management tool for BitBrowser.

## Table of Contents

### Getting Started

- [Quick Start](./quickstart.md) - Installation, setup, and first-time usage guide
- [Configuration Guide](./configuration.md) - Detailed configuration options and best practices

### Core Concepts

- [System Architecture](./architecture.md) - System design and component overview
- [Database Design](./database.md) - Database schema, operations, and management
- [Task System](./task-system.md) - Task types, execution flow, and concurrency control
- [Browser Management](./browser-management.md) - Window management, proxy configuration, and Playwright integration

## Quick Links

### Installation

```bash
# Clone repository
git clone https://github.com/yourusername/auto_bitbrowser.git
cd auto_bitbrowser

# Install dependencies
uv sync
playwright install chromium

# Install frontend dependencies
cd web/frontend && npm install && cd ../..

# Start services
./start_web.sh
```

### Access

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## Key Features

- **Account Management**: Import, manage, and track Google accounts
- **Browser Automation**: Control BitBrowser windows via Playwright
- **Task Execution**: Automated 2FA setup, age verification, and card binding
- **Real-time Progress**: WebSocket-based progress tracking and logging
- **Concurrent Processing**: Multi-account parallel task execution

## System Requirements

- **Python**: 3.11 or higher
- **Node.js**: 18 or higher
- **Memory**: 8GB minimum (16GB recommended)
- **BitBrowser**: Fingerprint browser client

## Architecture Overview

```
Frontend (Vue 3) ↔ Backend (FastAPI) ↔ Database (SQLite)
                        ↓
                Automation Scripts (Playwright)
                        ↓
                BitBrowser API
                        ↓
                Browser Instances
```

## Task Types

| Task | Description | Script |
|------|-------------|--------|
| Setup 2FA | Initial 2FA secret key setup | `setup_2fa.py` |
| Reset 2FA | Modify existing 2FA key | `reset_2fa.py` |
| Age Verification | Verify age using virtual card | `age_verification.py` |
| Get SheerLink | Obtain student verification link | `run_playwright_google.py` |
| Bind Card | Automatic card binding and subscription | `auto_bind_card.py` |

## Configuration Files

- `accounts.txt` - Account information (email, password, backup email, 2FA secret)
- `cards.txt` - Virtual card information (card number, expiration, CVV)
- `proxies.txt` - Proxy configuration (socks5/http proxies)
- `accounts.db` - SQLite database (accounts and configuration)

## API Endpoints

### Accounts
- `GET /accounts` - List accounts
- `POST /accounts` - Create account
- `PUT /accounts/{email}` - Update account
- `DELETE /accounts/{email}` - Delete account
- `POST /accounts/import` - Import from file

### Browsers
- `GET /browsers` - List browser windows
- `POST /browsers/restore` - Restore windows
- `POST /browsers/sync` - Sync window information
- `POST /browsers/sync-2fa` - Sync 2FA to browsers

### Tasks
- `POST /tasks` - Create and execute task
- `GET /tasks/{task_id}` - Get task status
- `WS /ws` - WebSocket for real-time updates

### Configuration
- `GET /config` - Get all configuration
- `PUT /config` - Update configuration

## Database Schema

### accounts Table

| Field | Type | Description |
|-------|------|-------------|
| email | TEXT | Account email (primary key) |
| password | TEXT | Account password |
| backup_email | TEXT | Backup email |
| fa_secret | TEXT | 2FA secret key |
| browser_id | TEXT | BitBrowser window ID |
| status | TEXT | Account status |
| sheer_link | TEXT | SheerID verification link |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Last update time |

### config Table

| Field | Type | Description |
|-------|------|-------------|
| key | TEXT | Configuration key (primary key) |
| value | TEXT | Configuration value |

## Account Status Flow

```
pending → link_ready → verified → subscribed
   ↓           ↓           ↓           ↓
error / ineligible (any status can transition to these)
```

## Development

### Project Structure

```
auto_bitbrowser/
├── web/
│   ├── backend/          # FastAPI backend
│   │   ├── main.py       # Entry point
│   │   ├── routers/      # API routes
│   │   ├── schemas.py    # Pydantic models
│   │   └── websocket.py  # WebSocket manager
│   └── frontend/         # Vue 3 frontend
│       └── src/
│           ├── views/    # Page components
│           └── api/      # API client
├── automation-scripts/   # Playwright scripts
├── database.py           # Database manager
├── bit_api.py           # BitBrowser API wrapper
└── create_window.py     # Window management
```

### Tech Stack

**Backend**:
- FastAPI - Web framework
- Uvicorn - ASGI server
- Pydantic - Data validation
- SQLite - Database
- Playwright - Browser automation

**Frontend**:
- Vue 3 - UI framework
- Vite - Build tool
- Tailwind CSS - Styling
- Axios - HTTP client

## Best Practices

1. **Regular Backups**: Backup `accounts.db` regularly
2. **Secure Configuration**: Don't commit sensitive files to Git
3. **Concurrency Control**: Set appropriate concurrency based on system resources
4. **Error Handling**: Monitor logs and handle errors promptly
5. **Proxy Management**: Use quality proxies and rotate regularly
6. **Window Cleanup**: Delete unused browser windows periodically

## Troubleshooting

### Common Issues

1. **Backend won't start**: Ensure virtual environment is activated
2. **Frontend can't connect**: Check if backend is running on port 8000
3. **BitBrowser API error**: Verify BitBrowser client is running
4. **Playwright connection failed**: Check browser window is open
5. **Task execution failed**: Review logs for specific error messages

### Debug Commands

```bash
# Check backend
curl http://localhost:8000/accounts

# Check BitBrowser API
curl http://127.0.0.1:54345/browser/list

# View database
sqlite3 accounts.db "SELECT * FROM accounts LIMIT 5;"

# Check logs
tail -f app.log
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Support

- **Documentation**: Read the guides in this directory
- **Issues**: Report bugs on GitHub Issues
- **Logs**: Check backend logs and frontend console for errors

## License

[Your License Here]

## Changelog

See [CHANGELOG.md](../../CHANGELOG.md) for version history and updates.

---

**Note**: This is an automation tool for educational purposes. Use responsibly and in accordance with Google's Terms of Service and applicable laws.
