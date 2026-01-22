# Task System

## Overview

The task system is the core functionality of Auto BitBrowser, responsible for orchestrating and executing various automation tasks. The system supports multi-account concurrent processing, real-time progress push, and flexible task configuration.

## Task Types

### Supported Tasks

| Task Type | Value | Description | Script File |
|-----------|-------|-------------|-------------|
| Setup 2FA | `setup_2fa` | Initial 2FA secret key setup | `setup_2fa.py` |
| Reset 2FA | `reset_2fa` | Modify existing 2FA secret key | `reset_2fa.py` |
| Age Verification | `age_verification` | Verify age using virtual card | `age_verification.py` |
| Get SheerLink | `get_sheerlink` | Get student verification link | `run_playwright_google.py` |
| Bind Card | `bind_card` | Automatic card binding and subscription | `auto_bind_card.py` |

### Task Dependencies

```
setup_2fa (Setup 2FA)
  ↓
age_verification (Age Verification)
  ↓
get_sheerlink (Get Verification Link)
  ↓
bind_card (Bind Card and Subscribe)
```

**Note**:
- `reset_2fa` can be executed independently (modify existing 2FA)
- Other tasks are recommended to be executed in sequence

## Task Execution Flow

### 1. Task Creation

**API Endpoint**: `POST /tasks`

**Request Parameters**:
```json
{
  "task_types": ["setup_2fa", "age_verification"],
  "emails": ["user1@gmail.com", "user2@gmail.com"],
  "close_after": true,
  "concurrency": 2
}
```

**Response**:
```json
{
  "task_id": "task_1234567890",
  "message": "Task created"
}
```

### 2. Task Execution

**Executor**: `TaskExecutor` class (`web/backend/routers/tasks.py`)

**Execution Steps**:

```python
async def execute_task(task_id, task_types, emails, close_after, concurrency):
    # 1. Initialize progress
    progress = {
        "task_id": task_id,
        "status": "running",
        "total": len(emails),
        "completed": 0
    }

    # 2. Create semaphore to control concurrency
    semaphore = asyncio.Semaphore(concurrency)

    # 3. Create task list
    tasks = []
    for email in emails:
        task = process_account(email, task_types, semaphore, close_after)
        tasks.append(task)

    # 4. Execute concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 5. Update final status
    progress["status"] = "completed"
    progress["completed"] = len(emails)

    return results
```

### 3. Account Processing

**Processing Function**: `process_account()`

```python
async def process_account(email, task_types, semaphore, close_after):
    async with semaphore:  # Control concurrency
        # 1. Get account info from database
        account = get_account(email)

        # 2. Open browser window
        browser_id = account.get('browser_id')
        if not browser_id:
            browser_id = await create_browser_window(account)

        ws_endpoint = await open_browser(browser_id)

        # 3. Execute tasks sequentially
        for task_type in task_types:
            success = await execute_single_task(
                task_type, account, ws_endpoint
            )

            if not success:
                break  # Task failed, stop subsequent tasks

        # 4. Close browser (optional)
        if close_after:
            await close_browser(browser_id)

        return success
```

### 4. Single Task Execution

**Execution Function**: `execute_single_task()`

```python
async def execute_single_task(task_type, account, ws_endpoint):
    # Call corresponding script based on task type
    if task_type == "setup_2fa":
        success, message = await run_setup_2fa(account, ws_endpoint)
    elif task_type == "reset_2fa":
        success, message = await run_reset_2fa(account, ws_endpoint)
    elif task_type == "age_verification":
        success, message = await run_age_verification(account, ws_endpoint)
    elif task_type == "get_sheerlink":
        success, message = await run_get_sheerlink(account, ws_endpoint)
    elif task_type == "bind_card":
        success, message = await run_bind_card(account, ws_endpoint)

    # Update account status
    if success:
        update_account_status(account['email'], get_success_status(task_type))
    else:
        update_account_status(account['email'], 'error')

    # Push progress
    await broadcast_progress(account['email'], task_type, success, message)

    return success
```

## Concurrency Control

### Semaphore

Use `asyncio.Semaphore` to limit the number of simultaneously running browsers:

```python
# Create semaphore (max 3 concurrent)
semaphore = asyncio.Semaphore(3)

# Use in task
async with semaphore:
    # At most 3 executing simultaneously here
    await process_account(email)
```

**Why Concurrency Control?**
- Browsers consume significant memory and CPU
- BitBrowser API has concurrency limits
- Avoid triggering Google's risk control mechanisms

### Recommended Concurrency Levels

| Machine Configuration | Recommended Concurrency |
|----------------------|------------------------|
| 8GB RAM | 1-2 |
| 16GB RAM | 2-3 |
| 32GB RAM | 3-5 |

## Progress Push

### WebSocket Messages

**Task Progress**:
```python
await manager.broadcast({
    "type": "progress",
    "data": {
        "task_id": task_id,
        "status": "running",
        "completed": 5,
        "total": 10,
        "message": "Processing account 5"
    }
})
```

**Account Progress**:
```python
await manager.broadcast({
    "type": "account_progress",
    "data": {
        "email": "user@gmail.com",
        "status": "running",
        "currentTask": "Setup 2FA",
        "message": "Generating secret key..."
    }
})
```

**Log Message**:
```python
await manager.broadcast({
    "type": "log",
    "data": {
        "time": "12:34:56",
        "level": "info",
        "email": "user@gmail.com",
        "message": "2FA setup successful"
    }
})
```

### Frontend Reception

```javascript
// Connect WebSocket
const ws = new WebSocket('ws://localhost:8000/ws')

// Receive messages
ws.onmessage = (event) => {
  const message = JSON.parse(event.data)

  if (message.type === 'progress') {
    updateProgress(message.data)
  } else if (message.type === 'account_progress') {
    updateAccountProgress(message.data)
  } else if (message.type === 'log') {
    appendLog(message.data)
  }
}
```

## Task Configuration

### Configuration Sources

Configuration information needed for task execution:

1. **Account Information**: Read from database `accounts` table
2. **Card Information**: Read from database `config` table
3. **API Key**: Read from database `config` table

### Configuration Priority

```
Database Configuration > Environment Variables > Default Values
```

**Example**:
```python
# Get card number
card_number = get_config('card_number') or os.getenv('CARD_NUMBER') or ''
```

## Error Handling

### Error Types

| Error Type | Handling Method | Continue? |
|------------|----------------|-----------|
| Account not found | Skip account | Yes |
| Browser open failed | Retry 3 times | No |
| Script execution failed | Log error, update status | No |
| Network timeout | Retry 2 times | No |
| Missing configuration | Prompt user to configure | No |

### Error Recovery

```python
async def execute_with_retry(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

### Error Logging

```python
def log_error(email, task_type, error):
    logger.error(f"[{email}] {task_type} failed: {error}")

    # Push to frontend
    await broadcast_log({
        "level": "error",
        "email": email,
        "message": f"{task_type} failed: {error}"
    })

    # Update database
    update_account_status(email, 'error')
```

## Task Status

### Task Status Flow

```
pending (Pending)
  ↓
running (Running)
  ↓
completed (Completed) / failed (Failed)
```

### Account Status Updates

Account status updated after different tasks succeed:

| Task Type | Status After Success |
|-----------|---------------------|
| `setup_2fa` | Keep original status |
| `reset_2fa` | Keep original status |
| `age_verification` | Keep original status |
| `get_sheerlink` | `link_ready` |
| `bind_card` | `subscribed` |

## Task Queue

### Current Implementation

Currently uses `asyncio.gather()` for concurrent task execution, no persistent queue.

### Future Improvements

Can use Celery or RQ to implement persistent task queue:

```python
# Using Celery
@celery.task
def process_account_task(email, task_types):
    # Task logic
    pass

# Submit task
for email in emails:
    process_account_task.delay(email, task_types)
```

## Task Scheduling

### Scheduled Tasks

Can use APScheduler to implement scheduled tasks:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

# Execute daily at 2 AM
@scheduler.scheduled_job('cron', hour=2)
async def daily_task():
    # Execute task
    pass

scheduler.start()
```

### Task Dependencies

Can use Celery Chain to implement task dependencies:

```python
from celery import chain

# Execute in sequence
workflow = chain(
    setup_2fa.s(email),
    age_verification.s(),
    get_sheerlink.s(),
    bind_card.s()
)

workflow.apply_async()
```

## Performance Optimization

### 1. Batch Database Operations

```python
# Batch update status
def batch_update_status(emails, status):
    with DBManager.get_db() as conn:
        cursor = conn.cursor()
        cursor.executemany(
            "UPDATE accounts SET status = ? WHERE email = ?",
            [(status, email) for email in emails]
        )
        conn.commit()
```

### 2. Connection Reuse

```python
# Reuse browser connections
browser_connections = {}

async def get_browser_connection(browser_id):
    if browser_id not in browser_connections:
        browser_connections[browser_id] = await connect_browser(browser_id)
    return browser_connections[browser_id]
```

### 3. Async I/O

```python
# Use asyncio for concurrent execution
tasks = [
    asyncio.create_task(process_account(email))
    for email in emails
]
results = await asyncio.gather(*tasks)
```

## Monitoring and Statistics

### Task Statistics

```python
def get_task_stats(task_id):
    return {
        "total": 100,
        "completed": 80,
        "failed": 5,
        "running": 15,
        "success_rate": 0.94,
        "avg_duration": 45.2  # seconds
    }
```

### Performance Metrics

- **Task Throughput**: Accounts processed per minute
- **Success Rate**: Successful accounts / Total accounts
- **Average Duration**: Average processing time per account
- **Concurrency Level**: Number of simultaneously running tasks

## Best Practices

1. **Set Reasonable Concurrency**: Adjust based on machine configuration
2. **Task Order**: Execute tasks according to dependencies
3. **Error Handling**: Catch and log all exceptions
4. **Progress Push**: Update frontend progress promptly
5. **Resource Cleanup**: Close browsers after task completion
6. **Data Backup**: Backup database before tasks
7. **Log Recording**: Record detailed task execution logs
8. **Timeout Control**: Set reasonable timeout periods

## Troubleshooting

### Task Stuck

**Causes**:
- Browser unresponsive
- Network timeout
- Deadlock

**Solutions**:
```python
# Set timeout
async with asyncio.timeout(300):  # 5 minute timeout
    await process_account(email)
```

### High Task Failure Rate

**Causes**:
- Configuration errors
- Account issues
- Network problems

**Solutions**:
1. Check if configuration is correct
2. Verify account information
3. Check network connection
4. View detailed logs

### High Memory Usage

**Causes**:
- Concurrency too high
- Browsers not closed
- Memory leak

**Solutions**:
1. Reduce concurrency level
2. Ensure browsers are closed after task completion
3. Restart service regularly

## Example Code

### Complete Task Execution Flow

```python
async def execute_task_example():
    # 1. Create task
    task_id = generate_task_id()
    emails = ["user1@gmail.com", "user2@gmail.com"]
    task_types = ["setup_2fa", "age_verification"]
    concurrency = 2

    # 2. Initialize progress
    progress = {
        "task_id": task_id,
        "status": "running",
        "total": len(emails),
        "completed": 0
    }
    await broadcast_progress(progress)

    # 3. Create semaphore
    semaphore = asyncio.Semaphore(concurrency)

    # 4. Create task list
    tasks = []
    for email in emails:
        task = process_account_with_semaphore(
            email, task_types, semaphore
        )
        tasks.append(task)

    # 5. Execute concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 6. Collect statistics
    success_count = sum(1 for r in results if r is True)
    failed_count = len(results) - success_count

    # 7. Update final status
    progress["status"] = "completed"
    progress["completed"] = len(emails)
    progress["message"] = f"Success: {success_count}, Failed: {failed_count}"
    await broadcast_progress(progress)

    return results

async def process_account_with_semaphore(email, task_types, semaphore):
    async with semaphore:
        try:
            # Get account info
            account = get_account(email)
            if not account:
                raise ValueError(f"Account not found: {email}")

            # Open browser
            browser_id = account.get('browser_id')
            if not browser_id:
                browser_id = await create_browser_window(account)

            ws_endpoint = await open_browser(browser_id)

            # Execute tasks
            for task_type in task_types:
                await broadcast_account_progress(email, task_type, "running")

                success, message = await execute_single_task(
                    task_type, account, ws_endpoint
                )

                if success:
                    await broadcast_account_progress(
                        email, task_type, "completed", message
                    )
                else:
                    await broadcast_account_progress(
                        email, task_type, "failed", message
                    )
                    return False

            # Close browser
            await close_browser(browser_id)

            return True

        except Exception as e:
            logger.error(f"[{email}] Task execution failed: {e}")
            await broadcast_log("error", email, str(e))
            return False
```
