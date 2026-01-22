# 任务系统

## 概述

任务系统是 Auto BitBrowser 的核心功能，负责编排和执行各种自动化任务。系统支持多账号并发处理，实时进度推送，以及灵活的任务配置。

## 任务类型

### 支持的任务

| 任务类型 | 值 | 说明 | 脚本文件 |
|---------|---|------|---------|
| 设置 2FA | `setup_2fa` | 首次设置 2FA 密钥 | `setup_2fa.py` |
| 修改 2FA | `reset_2fa` | 修改现有 2FA 密钥 | `reset_2fa.py` |
| 年龄验证 | `age_verification` | 使用虚拟卡验证年龄 | `age_verification.py` |
| 获取 SheerLink | `get_sheerlink` | 获取学生验证链接 | `run_playwright_google.py` |
| 绑卡订阅 | `bind_card` | 自动绑卡并订阅 | `auto_bind_card.py` |

### 任务依赖关系

```
setup_2fa (设置 2FA)
  ↓
age_verification (年龄验证)
  ↓
get_sheerlink (获取验证链接)
  ↓
bind_card (绑卡订阅)
```

**注意**:
- `reset_2fa` 可以独立执行（修改已有 2FA）
- 其他任务建议按顺序执行

## 任务执行流程

### 1. 任务创建

**API 端点**: `POST /tasks`

**请求参数**:
```json
{
  "task_types": ["setup_2fa", "age_verification"],
  "emails": ["user1@gmail.com", "user2@gmail.com"],
  "close_after": true,
  "concurrency": 2
}
```

**响应**:
```json
{
  "task_id": "task_1234567890",
  "message": "任务已创建"
}
```

### 2. 任务执行

**执行器**: `TaskExecutor` 类 (`web/backend/routers/tasks.py`)

**执行步骤**:

```python
async def execute_task(task_id, task_types, emails, close_after, concurrency):
    # 1. 初始化进度
    progress = {
        "task_id": task_id,
        "status": "running",
        "total": len(emails),
        "completed": 0
    }

    # 2. 创建信号量控制并发
    semaphore = asyncio.Semaphore(concurrency)

    # 3. 创建任务列表
    tasks = []
    for email in emails:
        task = process_account(email, task_types, semaphore, close_after)
        tasks.append(task)

    # 4. 并发执行
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 5. 更新最终状态
    progress["status"] = "completed"
    progress["completed"] = len(emails)

    return results
```

### 3. 账号处理

**处理函数**: `process_account()`

```python
async def process_account(email, task_types, semaphore, close_after):
    async with semaphore:  # 控制并发数
        # 1. 从数据库获取账号信息
        account = get_account(email)

        # 2. 打开浏览器窗口
        browser_id = account.get('browser_id')
        if not browser_id:
            browser_id = await create_browser_window(account)

        ws_endpoint = await open_browser(browser_id)

        # 3. 依次执行任务
        for task_type in task_types:
            success = await execute_single_task(
                task_type, account, ws_endpoint
            )

            if not success:
                break  # 任务失败，停止后续任务

        # 4. 关闭浏览器（可选）
        if close_after:
            await close_browser(browser_id)

        return success
```

### 4. 单个任务执行

**执行函数**: `execute_single_task()`

```python
async def execute_single_task(task_type, account, ws_endpoint):
    # 根据任务类型调用对应的脚本
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

    # 更新账号状态
    if success:
        update_account_status(account['email'], get_success_status(task_type))
    else:
        update_account_status(account['email'], 'error')

    # 推送进度
    await broadcast_progress(account['email'], task_type, success, message)

    return success
```

## 并发控制

### Semaphore 信号量

使用 `asyncio.Semaphore` 限制同时运行的浏览器数量：

```python
# 创建信号量（最多 3 个并发）
semaphore = asyncio.Semaphore(3)

# 在任务中使用
async with semaphore:
    # 这里最多同时执行 3 个
    await process_account(email)
```

**为什么需要并发控制？**
- 浏览器占用大量内存和 CPU
- BitBrowser API 有并发限制
- 避免触发 Google 的风控机制

### 推荐并发数

| 机器配置 | 推荐并发数 |
|---------|-----------|
| 8GB 内存 | 1-2 |
| 16GB 内存 | 2-3 |
| 32GB 内存 | 3-5 |

## 进度推送

### WebSocket 消息

**任务进度**:
```python
await manager.broadcast({
    "type": "progress",
    "data": {
        "task_id": task_id,
        "status": "running",
        "completed": 5,
        "total": 10,
        "message": "正在处理第 5 个账号"
    }
})
```

**账号进度**:
```python
await manager.broadcast({
    "type": "account_progress",
    "data": {
        "email": "user@gmail.com",
        "status": "running",
        "currentTask": "设置 2FA",
        "message": "正在生成密钥..."
    }
})
```

**日志消息**:
```python
await manager.broadcast({
    "type": "log",
    "data": {
        "time": "12:34:56",
        "level": "info",
        "email": "user@gmail.com",
        "message": "2FA 设置成功"
    }
})
```

### 前端接收

```javascript
// 连接 WebSocket
const ws = new WebSocket('ws://localhost:8000/ws')

// 接收消息
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

## 任务配置

### 配置来源

任务执行时需要的配置信息：

1. **账号信息**: 从数据库 `accounts` 表读取
2. **卡信息**: 从数据库 `config` 表读取
3. **API Key**: 从数据库 `config` 表读取

### 配置优先级

```
数据库配置 > 环境变量 > 默认值
```

**示例**:
```python
# 获取卡号
card_number = get_config('card_number') or os.getenv('CARD_NUMBER') or ''
```

## 错误处理

### 错误类型

| 错误类型 | 处理方式 | 是否继续 |
|---------|---------|---------|
| 账号不存在 | 跳过该账号 | 是 |
| 浏览器打开失败 | 重试 3 次 | 否 |
| 脚本执行失败 | 记录错误，更新状态 | 否 |
| 网络超时 | 重试 2 次 | 否 |
| 配置缺失 | 提示用户配置 | 否 |

### 错误恢复

```python
async def execute_with_retry(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # 指数退避
```

### 错误日志

```python
def log_error(email, task_type, error):
    logger.error(f"[{email}] {task_type} 失败: {error}")

    # 推送到前端
    await broadcast_log({
        "level": "error",
        "email": email,
        "message": f"{task_type} 失败: {error}"
    })

    # 更新数据库
    update_account_status(email, 'error')
```

## 任务状态

### 任务状态流转

```
pending (待执行)
  ↓
running (执行中)
  ↓
completed (已完成) / failed (失败)
```

### 账号状态更新

不同任务成功后更新的账号状态：

| 任务类型 | 成功后状态 |
|---------|-----------|
| `setup_2fa` | 保持原状态 |
| `reset_2fa` | 保持原状态 |
| `age_verification` | 保持原状态 |
| `get_sheerlink` | `link_ready` |
| `bind_card` | `subscribed` |

## 任务队列

### 当前实现

目前使用 `asyncio.gather()` 并发执行任务，没有持久化队列。

### 未来改进

可以使用 Celery 或 RQ 实现持久化任务队列：

```python
# 使用 Celery
@celery.task
def process_account_task(email, task_types):
    # 任务逻辑
    pass

# 提交任务
for email in emails:
    process_account_task.delay(email, task_types)
```

## 任务调度

### 定时任务

可以使用 APScheduler 实现定时任务：

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

# 每天凌晨 2 点执行
@scheduler.scheduled_job('cron', hour=2)
async def daily_task():
    # 执行任务
    pass

scheduler.start()
```

### 任务依赖

可以使用 Celery Chain 实现任务依赖：

```python
from celery import chain

# 按顺序执行
workflow = chain(
    setup_2fa.s(email),
    age_verification.s(),
    get_sheerlink.s(),
    bind_card.s()
)

workflow.apply_async()
```

## 性能优化

### 1. 批量数据库操作

```python
# 批量更新状态
def batch_update_status(emails, status):
    with DBManager.get_db() as conn:
        cursor = conn.cursor()
        cursor.executemany(
            "UPDATE accounts SET status = ? WHERE email = ?",
            [(status, email) for email in emails]
        )
        conn.commit()
```

### 2. 连接复用

```python
# 复用浏览器连接
browser_connections = {}

async def get_browser_connection(browser_id):
    if browser_id not in browser_connections:
        browser_connections[browser_id] = await connect_browser(browser_id)
    return browser_connections[browser_id]
```

### 3. 异步 I/O

```python
# 使用 asyncio 并发执行
tasks = [
    asyncio.create_task(process_account(email))
    for email in emails
]
results = await asyncio.gather(*tasks)
```

## 监控与统计

### 任务统计

```python
def get_task_stats(task_id):
    return {
        "total": 100,
        "completed": 80,
        "failed": 5,
        "running": 15,
        "success_rate": 0.94,
        "avg_duration": 45.2  # 秒
    }
```

### 性能指标

- **任务吞吐量**: 每分钟处理的账号数
- **成功率**: 成功账号数 / 总账号数
- **平均耗时**: 单个账号的平均处理时间
- **并发数**: 同时运行的任务数

## 最佳实践

1. **合理设置并发数**: 根据机器配置调整
2. **任务顺序**: 按依赖关系执行任务
3. **错误处理**: 捕获并记录所有异常
4. **进度推送**: 及时更新前端进度
5. **资源清理**: 任务结束后关闭浏览器
6. **数据备份**: 任务前备份数据库
7. **日志记录**: 详细记录任务执行日志
8. **超时控制**: 设置合理的超时时间

## 故障排查

### 任务卡住

**原因**:
- 浏览器无响应
- 网络超时
- 死锁

**解决**:
```python
# 设置超时
async with asyncio.timeout(300):  # 5 分钟超时
    await process_account(email)
```

### 任务失败率高

**原因**:
- 配置错误
- 账号问题
- 网络问题

**解决**:
1. 检查配置是否正确
2. 验证账号信息
3. 检查网络连接
4. 查看详细日志

### 内存占用过高

**原因**:
- 并发数过高
- 浏览器未关闭
- 内存泄漏

**解决**:
1. 降低并发数
2. 确保任务结束后关闭浏览器
3. 定期重启服务

## 示例代码

### 完整任务执行流程

```python
async def execute_task_example():
    # 1. 创建任务
    task_id = generate_task_id()
    emails = ["user1@gmail.com", "user2@gmail.com"]
    task_types = ["setup_2fa", "age_verification"]
    concurrency = 2

    # 2. 初始化进度
    progress = {
        "task_id": task_id,
        "status": "running",
        "total": len(emails),
        "completed": 0
    }
    await broadcast_progress(progress)

    # 3. 创建信号量
    semaphore = asyncio.Semaphore(concurrency)

    # 4. 创建任务列表
    tasks = []
    for email in emails:
        task = process_account_with_semaphore(
            email, task_types, semaphore
        )
        tasks.append(task)

    # 5. 并发执行
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 6. 统计结果
    success_count = sum(1 for r in results if r is True)
    failed_count = len(results) - success_count

    # 7. 更新最终状态
    progress["status"] = "completed"
    progress["completed"] = len(emails)
    progress["message"] = f"成功: {success_count}, 失败: {failed_count}"
    await broadcast_progress(progress)

    return results

async def process_account_with_semaphore(email, task_types, semaphore):
    async with semaphore:
        try:
            # 获取账号信息
            account = get_account(email)
            if not account:
                raise ValueError(f"账号不存在: {email}")

            # 打开浏览器
            browser_id = account.get('browser_id')
            if not browser_id:
                browser_id = await create_browser_window(account)

            ws_endpoint = await open_browser(browser_id)

            # 执行任务
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

            # 关闭浏览器
            await close_browser(browser_id)

            return True

        except Exception as e:
            logger.error(f"[{email}] 任务执行失败: {e}")
            await broadcast_log("error", email, str(e))
            return False
```
