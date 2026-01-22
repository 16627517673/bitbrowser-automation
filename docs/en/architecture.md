# System Architecture

## Overview

Auto BitBrowser adopts a frontend-backend separation architecture, implementing real-time communication through WebSocket, and using Playwright with BitBrowser API for browser automation control.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        User Interface Layer                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Vue 3 Frontend (http://localhost:5173)              │   │
│  │  - Accounts Management Page (AccountsView)           │   │
│  │  - Browser Management Page (BrowsersView)            │   │
│  │  - Task Execution Page (TasksView)                   │   │
│  │  - WebSocket Real-time Communication                 │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↕ HTTP/WebSocket
┌─────────────────────────────────────────────────────────────┐
│                        Application Service Layer              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  FastAPI Backend (http://localhost:8000)             │   │
│  │  ┌────────────┬────────────┬────────────┬──────────┐ │   │
│  │  │ Accounts   │ Browsers   │ Tasks      │ Config   │ │   │
│  │  │ Router     │ Router     │ Router     │ Router   │ │   │
│  │  └────────────┴────────────┴────────────┴──────────┘ │   │
│  │  ┌──────────────────────────────────────────────────┐ │   │
│  │  │  WebSocket Manager (Real-time Progress Push)     │ │   │
│  │  └──────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                        Data Persistence Layer                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  SQLite Database (accounts.db)                       │   │
│  │  - accounts table (account information)              │   │
│  │  - config table (configuration information)          │   │
│  │  DBManager (Thread-safe database manager)            │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                        Automation Execution Layer             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Playwright Automation Scripts                        │   │
│  │  ┌────────────┬────────────┬────────────┬──────────┐ │   │
│  │  │ setup_2fa  │ reset_2fa  │ age_       │ auto_    │ │   │
│  │  │            │            │ verification│ bind_card│ │   │
│  │  └────────────┴────────────┴────────────┴──────────┘ │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                        Browser Control Layer                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  BitBrowser API (http://127.0.0.1:54345)             │   │
│  │  - Create/Update Window (POST /browser/update)       │   │
│  │  - Open Window (POST /browser/open)                  │   │
│  │  - Close Window (POST /browser/close)                │   │
│  │  - Delete Window (POST /browser/delete)              │   │
│  │  - Get Window List (POST /browser/list)              │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                        Browser Instances                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Chromium Browser Windows (Fingerprint Isolation)    │   │
│  │  - Independent Cookie/LocalStorage                   │   │
│  │  - Independent Fingerprint Configuration             │   │
│  │  - Proxy IP Binding                                  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Frontend (Vue 3)

**Tech Stack**:
- Vue 3 (Composition API)
- Vite (Build tool)
- Tailwind CSS (Styling framework)
- Axios (HTTP client)

**Main Pages**:
- `AccountsView.vue`: Account management, supports import, search, filter, export
- `BrowsersView.vue`: Browser window management, create, restore, sync windows
- `TasksView.vue`: Task execution, select accounts, configure tasks, view progress

**State Management**:
- `websocket.js`: WebSocket connection management, real-time task progress and log reception

### 2. Backend (FastAPI)

**Tech Stack**:
- FastAPI (Web framework)
- Uvicorn (ASGI server)
- Pydantic (Data validation)
- asyncio (Async tasks)

**Router Modules**:
- `accounts.py`: Account CRUD, import/export, status updates
- `browsers.py`: Browser window management, 2FA sync
- `tasks.py`: Task creation, execution, progress management
- `config.py`: Configuration management (SheerID API Key, card info)

**WebSocket**:
- `websocket.py`: Real-time push of task progress, logs, account status

### 3. Data Layer (SQLite)

**Database Manager** (`database.py`):
- `DBManager`: Thread-safe database operation class
- Automatic table structure creation
- Support for importing data from text files

**Table Structure**:
- `accounts`: Account information (email, password, backup_email, fa_secret, browser_id, status, sheer_link)
- `config`: Configuration information (key-value storage)

### 4. Automation Layer (Playwright)

**Core Scripts**:
- `setup_2fa.py`: Initial 2FA setup, generate and save secret key
- `reset_2fa.py`: Modify existing 2FA secret key
- `age_verification.py`: Complete age verification using virtual card
- `run_playwright_google.py`: Get SheerID verification link
- `auto_bind_card.py`: Automatic card binding and subscription

**Browser Control**:
- `bit_api.py`: BitBrowser REST API wrapper
- `create_window.py`: Window creation, deletion, cloning
- `browser_manager.py`: Browser configuration persistence

### 5. External Services

**BitBrowser API**:
- Local service: `http://127.0.0.1:54345`
- Function: Create fingerprint-isolated browser windows
- Important: All requests must disable proxy (`proxies={'http': None, 'https': None}`)

**SheerID Verification Service**:
- Service address: `https://batch.1key.me`
- Function: Batch verify student eligibility
- Required: User-configured API Key

## Data Flow

### Task Execution Flow

```
1. User selects accounts and task types in frontend
   ↓
2. Frontend sends POST /tasks request to backend
   ↓
3. Backend creates task, returns task_id
   ↓
4. Backend starts async task executor
   ↓
5. Process accounts in batches by concurrency level
   ↓
6. For each account:
   a. Read account info from database
   b. Call BitBrowser API to open window
   c. Connect Playwright via CDP
   d. Execute automation script
   e. Update account status to database
   f. Push progress via WebSocket
   ↓
7. All accounts processed, task completed
   ↓
8. Frontend displays final results
```

### WebSocket Message Format

**Progress Update**:
```json
{
  "type": "progress",
  "data": {
    "task_id": "xxx",
    "status": "running",
    "completed": 5,
    "total": 10,
    "message": "Processing..."
  }
}
```

**Account Progress**:
```json
{
  "type": "account_progress",
  "data": {
    "email": "user@gmail.com",
    "status": "running",
    "currentTask": "Setup 2FA",
    "message": "Generating secret key..."
  }
}
```

**Log Message**:
```json
{
  "type": "log",
  "data": {
    "time": "12:34:56",
    "level": "info",
    "email": "user@gmail.com",
    "message": "2FA setup successful"
  }
}
```

## Concurrency Control

### Task Concurrency

Use `asyncio.Semaphore` to control the number of simultaneously running browsers:

```python
semaphore = asyncio.Semaphore(concurrency)  # Default 1

async with semaphore:
    # Execute task
    await process_account(account)
```

### Database Concurrency

Use thread locks to protect database operations:

```python
with DBManager.get_db() as conn:
    # Database operations
    cursor.execute(...)
```

## Error Handling

### Layered Error Handling

1. **Automation Script Layer**: Catch Playwright exceptions, return `(success, message)` tuple
2. **Task Execution Layer**: Catch script exceptions, update account status to `error`
3. **API Layer**: Catch all exceptions, return standard error response
4. **Frontend Layer**: Display error messages, log to console

### Retry Mechanism

- **Button Click**: Try multiple selectors, support `force=True` and `dispatchEvent`
- **Element Wait**: Use `wait_for_selector` and `is_visible()` checks
- **Network Requests**: Log failures when BitBrowser API calls fail

## Security Design

### Sensitive Information Protection

1. **Configuration Files**: Exclude sensitive files via `.gitignore`
2. **Database**: Local SQLite, not uploaded to version control
3. **API Key**: User-configured, no default value
4. **Passwords**: Stored in local database, not transmitted over network

### Access Control

- Backend API: Only listens on `localhost`, not exposed externally
- BitBrowser API: Local service, no authentication required
- WebSocket: Protected by same-origin policy

## Extensibility

### Adding New Task Types

1. Create new script in `automation-scripts/`
2. Add task handler function in `tasks.py`
3. Add task option in frontend `TasksView.vue`
4. Update `schemas.py` to add task type enum

### Adding New Configuration Items

1. Add configuration key in `config.py`
2. Update `ConfigUpdate` and `ConfigResponse` in `schemas.py`
3. Add input field in frontend config panel

## Performance Optimization

### Frontend Optimization

- Virtual Scrolling: Use virtual scrolling for large account lists
- Debouncing: Use debouncing for search input
- Lazy Loading: Route lazy loading

### Backend Optimization

- Async Processing: Use `asyncio` for concurrent task execution
- Database Indexing: Create indexes on `email` field
- WebSocket Batch Push: Merge multiple log messages

### Browser Optimization

- Window Reuse: Optionally keep windows open after task completion
- Concurrency Control: Limit number of simultaneously open browsers
- Resource Cleanup: Close unnecessary windows after task completion

## Deployment Recommendations

### Development Environment

```bash
# Backend
cd web/backend
uvicorn main:app --reload --port 8000

# Frontend
cd web/frontend
npm run dev
```

### Production Environment

```bash
# Backend (using gunicorn + uvicorn workers)
gunicorn web.backend.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Frontend (build static files)
cd web/frontend
npm run build
# Use nginx or other static server to host dist/
```

### Docker Deployment

```dockerfile
# Example Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install uv && uv sync
RUN cd web/frontend && npm install && npm run build

CMD ["uvicorn", "web.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Monitoring and Logging

### Log Levels

- `INFO`: Normal operation logs
- `WARNING`: Recoverable errors
- `ERROR`: Serious errors

### Log Output

- Console: Real-time viewing in development environment
- WebSocket: Real-time display in frontend
- File: Optional log file output configuration

## Technical Debt

### Known Limitations

1. **Single Machine Deployment**: Currently only supports single machine operation, no distributed support
2. **Database**: SQLite not suitable for high concurrency scenarios
3. **Authentication**: No user authentication system, local use only

### Future Improvements

1. Support PostgreSQL/MySQL
2. Add user authentication and permission management
3. Support distributed task queue (Celery/RQ)
4. Add task scheduling functionality (scheduled tasks)
