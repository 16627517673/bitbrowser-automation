# 浏览器管理

## 概述

Auto BitBrowser 通过 **BitBrowser API** 管理指纹浏览器窗口，实现账号隔离、代理配置和自动化控制。每个账号对应一个独立的浏览器窗口，拥有独立的 Cookie、LocalStorage 和指纹配置。

## BitBrowser API

### API 地址

```
http://127.0.0.1:54345
```

**重要**: 所有 API 请求必须禁用代理：

```python
import requests

response = requests.post(
    'http://127.0.0.1:54345/browser/update',
    json=data,
    proxies={'http': None, 'https': None}  # 必须禁用代理
)
```

### 核心接口

#### 1. 创建/更新窗口

**端点**: `POST /browser/update`

**请求参数**:
```json
{
  "id": "browser_123",  // 窗口 ID（可选，不提供则创建新窗口）
  "name": "账号1",
  "remark": "备注信息",
  "proxyMethod": 2,  // 代理类型：2=自定义, 3=无代理
  "proxyType": "socks5",  // socks5 或 http
  "host": "proxy.example.com",
  "port": "1080",
  "proxyAccount": "username",
  "proxyPassword": "password",
  "faSecretKey": "ABCD1234EFGH5678"  // 2FA 密钥
}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "id": "browser_123"
  }
}
```

#### 2. 打开窗口

**端点**: `POST /browser/open`

**请求参数**:
```json
{
  "id": "browser_123"
}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "http": "http://127.0.0.1:9222",
    "ws": "ws://127.0.0.1:9222/devtools/browser/xxx",
    "webdriver": "ws://127.0.0.1:9222/devtools/browser/xxx"
  }
}
```

**WebSocket 端点**用于 Playwright 连接：

```python
from playwright.async_api import async_playwright

async with async_playwright() as p:
    browser = await p.chromium.connect_over_cdp(ws_endpoint)
    page = await browser.new_page()
```

#### 3. 关闭窗口

**端点**: `POST /browser/close`

**请求参数**:
```json
{
  "id": "browser_123"
}
```

#### 4. 删除窗口

**端点**: `POST /browser/delete`

**请求参数**:
```json
{
  "ids": ["browser_123", "browser_456"]
}
```

#### 5. 获取窗口列表

**端点**: `POST /browser/list`

**请求参数**:
```json
{
  "page": 0,
  "pageSize": 100
}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "list": [
      {
        "id": "browser_123",
        "name": "账号1",
        "remark": "备注",
        "proxyMethod": 2,
        "faSecretKey": "ABCD1234"
      }
    ]
  }
}
```

## 窗口管理

### 窗口创建

**脚本**: `create_window.py`

**创建流程**:

```python
async def create_browser_window(account):
    """为账号创建浏览器窗口"""

    # 1. 准备窗口配置
    config = {
        "name": account['email'],
        "remark": f"Email: {account['email']}",
        "proxyMethod": 2,  # 自定义代理
        "proxyType": "socks5",
        "host": proxy_host,
        "port": proxy_port,
        "proxyAccount": proxy_user,
        "proxyPassword": proxy_pass,
        "faSecretKey": account.get('fa_secret', '')
    }

    # 2. 调用 API 创建窗口
    response = requests.post(
        'http://127.0.0.1:54345/browser/update',
        json=config,
        proxies={'http': None, 'https': None}
    )

    # 3. 获取窗口 ID
    browser_id = response.json()['data']['id']

    # 4. 保存到数据库
    update_account_browser_id(account['email'], browser_id)

    return browser_id
```

### 窗口恢复

**功能**: 从数据库恢复已有窗口配置

```python
async def restore_browser_windows():
    """恢复所有账号的浏览器窗口"""

    # 1. 获取所有账号
    accounts = get_all_accounts()

    # 2. 获取 BitBrowser 窗口列表
    existing_browsers = get_browser_list()
    existing_ids = {b['id'] for b in existing_browsers}

    # 3. 为没有窗口的账号创建窗口
    for account in accounts:
        if not account.get('browser_id'):
            browser_id = await create_browser_window(account)
            print(f"[创建] {account['email']} -> {browser_id}")
        elif account['browser_id'] not in existing_ids:
            # 窗口已被删除，重新创建
            browser_id = await create_browser_window(account)
            print(f"[重建] {account['email']} -> {browser_id}")
        else:
            print(f"[跳过] {account['email']} 窗口已存在")
```

### 窗口同步

**功能**: 同步数据库与 BitBrowser 的窗口信息

```python
async def sync_browser_windows():
    """同步窗口信息"""

    # 1. 获取 BitBrowser 窗口列表
    browsers = get_browser_list()

    # 2. 更新数据库中的窗口信息
    for browser in browsers:
        # 从备注中提取邮箱
        email = extract_email_from_remark(browser['remark'])
        if email:
            update_account_browser_id(email, browser['id'])

    # 3. 清理已删除的窗口
    all_browser_ids = {b['id'] for b in browsers}
    accounts = get_all_accounts()

    for account in accounts:
        if account.get('browser_id') and account['browser_id'] not in all_browser_ids:
            # 窗口已被删除，清空 browser_id
            update_account_browser_id(account['email'], None)
```

## 代理配置

### 代理类型

| proxyMethod | 说明 |
|-------------|------|
| 1 | 不使用代理 |
| 2 | 自定义代理 |
| 3 | 提取 IP |

### 代理格式

**Socks5**:
```
socks5://username:password@host:port
```

**HTTP**:
```
http://username:password@host:port
```

### 解析代理

```python
def parse_proxy(proxy_url):
    """解析代理 URL"""
    import re

    # socks5://user:pass@host:port
    match = re.match(r'(\w+)://([^:]+):([^@]+)@([^:]+):(\d+)', proxy_url)
    if match:
        return {
            "proxyType": match.group(1),
            "proxyAccount": match.group(2),
            "proxyPassword": match.group(3),
            "host": match.group(4),
            "port": match.group(5)
        }

    # socks5://host:port (无认证)
    match = re.match(r'(\w+)://([^:]+):(\d+)', proxy_url)
    if match:
        return {
            "proxyType": match.group(1),
            "host": match.group(2),
            "port": match.group(3)
        }

    return None
```

### 代理分配

```python
def assign_proxies(accounts, proxies):
    """为账号分配代理"""
    proxy_index = 0

    for account in accounts:
        if proxy_index < len(proxies):
            proxy = parse_proxy(proxies[proxy_index])
            account['proxy'] = proxy
            proxy_index += 1
        else:
            # 代理不足，循环使用
            proxy_index = 0

    return accounts
```

## 2FA 密钥管理

### 同步 2FA 到浏览器

**脚本**: `sync_2fa_to_browser.py`

```python
async def sync_2fa_to_browser(email):
    """同步 2FA 密钥到浏览器配置"""

    # 1. 从数据库获取账号信息
    account = get_account(email)
    if not account or not account.get('fa_secret'):
        return False, "账号不存在或未设置 2FA"

    # 2. 获取浏览器 ID
    browser_id = account.get('browser_id')
    if not browser_id:
        return False, "账号未关联浏览器窗口"

    # 3. 更新浏览器配置
    response = requests.post(
        'http://127.0.0.1:54345/browser/update',
        json={
            "id": browser_id,
            "faSecretKey": account['fa_secret']
        },
        proxies={'http': None, 'https': None}
    )

    if response.json().get('success'):
        return True, "2FA 密钥已同步"
    else:
        return False, "同步失败"
```

### 批量同步

```python
async def batch_sync_2fa():
    """批量同步所有账号的 2FA 密钥"""

    accounts = get_all_accounts()
    success_count = 0
    failed_count = 0

    for account in accounts:
        if account.get('fa_secret') and account.get('browser_id'):
            success, message = await sync_2fa_to_browser(account['email'])
            if success:
                success_count += 1
            else:
                failed_count += 1

    return success_count, failed_count
```

## Playwright 集成

### 连接浏览器

```python
from playwright.async_api import async_playwright

async def connect_to_browser(browser_id):
    """通过 CDP 连接到 BitBrowser 窗口"""

    # 1. 打开浏览器窗口
    response = requests.post(
        'http://127.0.0.1:54345/browser/open',
        json={"id": browser_id},
        proxies={'http': None, 'https': None}
    )

    # 2. 获取 WebSocket 端点
    ws_endpoint = response.json()['data']['ws']

    # 3. 连接 Playwright
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(ws_endpoint)
        context = browser.contexts[0]  # 使用已有的上下文
        page = context.pages[0] if context.pages else await context.new_page()

        return browser, page
```

### 执行自动化任务

```python
async def execute_automation(browser_id, task_func):
    """在浏览器中执行自动化任务"""

    try:
        # 连接浏览器
        browser, page = await connect_to_browser(browser_id)

        # 执行任务
        result = await task_func(page)

        # 关闭连接（不关闭浏览器窗口）
        await browser.close()

        return result

    except Exception as e:
        logger.error(f"自动化任务失败: {e}")
        return False, str(e)
```

## 窗口生命周期

### 创建窗口

```
1. 准备配置（账号、代理、2FA）
   ↓
2. 调用 /browser/update API
   ↓
3. 获取窗口 ID
   ↓
4. 保存到数据库
```

### 使用窗口

```
1. 从数据库获取 browser_id
   ↓
2. 调用 /browser/open API
   ↓
3. 获取 WebSocket 端点
   ↓
4. Playwright 连接
   ↓
5. 执行自动化任务
   ↓
6. 断开 Playwright 连接
```

### 删除窗口

```
1. 调用 /browser/close API（可选）
   ↓
2. 调用 /browser/delete API
   ↓
3. 从数据库清除 browser_id
```

## 窗口配置

### 完整配置示例

```json
{
  "id": "browser_123",
  "name": "user@gmail.com",
  "remark": "Email: user@gmail.com | Status: verified",
  "proxyMethod": 2,
  "proxyType": "socks5",
  "host": "proxy.example.com",
  "port": "1080",
  "proxyAccount": "username",
  "proxyPassword": "password",
  "faSecretKey": "ABCD1234EFGH5678",
  "fingerprint": {
    "ua": "Mozilla/5.0...",
    "language": "en-US",
    "timezone": "America/New_York",
    "webrtc": "disabled"
  }
}
```

### 指纹配置

BitBrowser 自动生成指纹配置，包括：

- User-Agent
- 屏幕分辨率
- 时区
- 语言
- WebRTC
- Canvas 指纹
- WebGL 指纹

## 最佳实践

1. **窗口命名**: 使用邮箱作为窗口名称，便于识别
2. **备注信息**: 在备注中记录账号状态和关键信息
3. **代理配置**: 每个账号使用独立代理，避免关联
4. **2FA 同步**: 设置 2FA 后立即同步到浏览器
5. **定期清理**: 删除不再使用的窗口
6. **窗口复用**: 任务完成后保持窗口打开，下次直接使用
7. **错误处理**: 捕获 API 调用异常，记录详细日志

## 故障排查

### 窗口打开失败

**原因**:
- BitBrowser 未启动
- 窗口 ID 不存在
- 端口被占用

**解决**:
```python
# 检查 BitBrowser 是否运行
response = requests.get('http://127.0.0.1:54345/browser/list')
if response.status_code != 200:
    print("BitBrowser 未启动")
```

### Playwright 连接失败

**原因**:
- WebSocket 端点错误
- 浏览器已关闭
- 网络问题

**解决**:
```python
# 重试连接
for attempt in range(3):
    try:
        browser = await p.chromium.connect_over_cdp(ws_endpoint)
        break
    except Exception as e:
        if attempt == 2:
            raise
        await asyncio.sleep(2)
```

### 代理不生效

**原因**:
- 代理配置错误
- 代理服务器不可用
- 代理认证失败

**解决**:
1. 检查代理格式是否正确
2. 测试代理连接
3. 验证代理账号密码

## API 封装

### bit_api.py

```python
import requests

BASE_URL = "http://127.0.0.1:54345"
PROXIES = {'http': None, 'https': None}

def create_or_update_browser(config):
    """创建或更新浏览器窗口"""
    response = requests.post(
        f"{BASE_URL}/browser/update",
        json=config,
        proxies=PROXIES
    )
    return response.json()

def open_browser(browser_id):
    """打开浏览器窗口"""
    response = requests.post(
        f"{BASE_URL}/browser/open",
        json={"id": browser_id},
        proxies=PROXIES
    )
    return response.json()

def close_browser(browser_id):
    """关闭浏览器窗口"""
    response = requests.post(
        f"{BASE_URL}/browser/close",
        json={"id": browser_id},
        proxies=PROXIES
    )
    return response.json()

def delete_browsers(browser_ids):
    """删除浏览器窗口"""
    response = requests.post(
        f"{BASE_URL}/browser/delete",
        json={"ids": browser_ids},
        proxies=PROXIES
    )
    return response.json()

def get_browser_list(page=0, page_size=100):
    """获取浏览器窗口列表"""
    response = requests.post(
        f"{BASE_URL}/browser/list",
        json={"page": page, "pageSize": page_size},
        proxies=PROXIES
    )
    return response.json()
```

## 性能优化

### 窗口池

```python
class BrowserPool:
    """浏览器窗口池"""

    def __init__(self, max_size=10):
        self.max_size = max_size
        self.pool = {}  # browser_id -> ws_endpoint

    async def get_browser(self, browser_id):
        """获取浏览器连接"""
        if browser_id in self.pool:
            return self.pool[browser_id]

        # 打开新窗口
        ws_endpoint = await open_browser(browser_id)
        self.pool[browser_id] = ws_endpoint

        # 限制池大小
        if len(self.pool) > self.max_size:
            # 关闭最旧的窗口
            oldest_id = next(iter(self.pool))
            await close_browser(oldest_id)
            del self.pool[oldest_id]

        return ws_endpoint

    async def close_all(self):
        """关闭所有窗口"""
        for browser_id in self.pool:
            await close_browser(browser_id)
        self.pool.clear()
```

### 批量操作

```python
async def batch_create_browsers(accounts, batch_size=10):
    """批量创建浏览器窗口"""

    for i in range(0, len(accounts), batch_size):
        batch = accounts[i:i + batch_size]

        # 并发创建
        tasks = [create_browser_window(acc) for acc in batch]
        results = await asyncio.gather(*tasks)

        # 等待一段时间，避免 API 限流
        await asyncio.sleep(1)

    return results
```
