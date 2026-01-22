# Browser Management

## Overview

Auto BitBrowser manages fingerprint browser windows through the **BitBrowser API**, implementing account isolation, proxy configuration, and automation control. Each account corresponds to an independent browser window with its own Cookie, LocalStorage, and fingerprint configuration.

## BitBrowser API

### API Address

```
http://127.0.0.1:54345
```

**Important**: All API requests must disable proxy:

```python
import requests

response = requests.post(
    'http://127.0.0.1:54345/browser/update',
    json=data,
    proxies={'http': None, 'https': None}  # Must disable proxy
)
```

### Core Endpoints

#### 1. Create/Update Window

**Endpoint**: `POST /browser/update`

**Request Parameters**:
```json
{
  "id": "browser_123",  // Window ID (optional, creates new if not provided)
  "name": "Account 1",
  "remark": "Remark information",
  "proxyMethod": 2,  // Proxy type: 2=custom, 3=no proxy
  "proxyType": "socks5",  // socks5 or http
  "host": "proxy.example.com",
  "port": "1080",
  "proxyAccount": "username",
  "proxyPassword": "password",
  "faSecretKey": "ABCD1234EFGH5678"  // 2FA secret key
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "id": "browser_123"
  }
}
```

#### 2. Open Window

**Endpoint**: `POST /browser/open`

**Request Parameters**:
```json
{
  "id": "browser_123"
}
```

**Response**:
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

**WebSocket endpoint** is used for Playwright connection:

```python
from playwright.async_api import async_playwright

async with async_playwright() as p:
    browser = await p.chromium.connect_over_cdp(ws_endpoint)
    page = await browser.new_page()
```

#### 3. Close Window

**Endpoint**: `POST /browser/close`

**Request Parameters**:
```json
{
  "id": "browser_123"
}
```

#### 4. Delete Window

**Endpoint**: `POST /browser/delete`

**Request Parameters**:
```json
{
  "ids": ["browser_123", "browser_456"]
}
```

#### 5. Get Window List

**Endpoint**: `POST /browser/list`

**Request Parameters**:
```json
{
  "page": 0,
  "pageSize": 100
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "list": [
      {
        "id": "browser_123",
        "name": "Account 1",
        "remark": "Remark",
        "proxyMethod": 2,
        "faSecretKey": "ABCD1234"
      }
    ]
  }
}
```

## Window Management

### Window Creation

**Script**: `create_window.py`

**Creation Flow**:

```python
async def create_browser_window(account):
    """Create browser window for account"""

    # 1. Prepare window configuration
    config = {
        "name": account['email'],
        "remark": f"Email: {account['email']}",
        "proxyMethod": 2,  # Custom proxy
        "proxyType": "socks5",
        "host": proxy_host,
        "port": proxy_port,
        "proxyAccount": proxy_user,
        "proxyPassword": proxy_pass,
        "faSecretKey": account.get('fa_secret', '')
    }

    # 2. Call API to create window
    response = requests.post(
        'http://127.0.0.1:54345/browser/update',
        json=config,
        proxies={'http': None, 'https': None}
    )

    # 3. Get window ID
    browser_id = response.json()['data']['id']

    # 4. Save to database
    update_account_browser_id(account['email'], browser_id)

    return browser_id
```

### Window Restoration

**Function**: Restore existing window configuration from database

```python
async def restore_browser_windows():
    """Restore browser windows for all accounts"""

    # 1. Get all accounts
    accounts = get_all_accounts()

    # 2. Get BitBrowser window list
    existing_browsers = get_browser_list()
    existing_ids = {b['id'] for b in existing_browsers}

    # 3. Create windows for accounts without windows
    for account in accounts:
        if not account.get('browser_id'):
            browser_id = await create_browser_window(account)
            print(f"[Created] {account['email']} -> {browser_id}")
        elif account['browser_id'] not in existing_ids:
            # Window was deleted, recreate
            browser_id = await create_browser_window(account)
            print(f"[Rebuilt] {account['email']} -> {browser_id}")
        else:
            print(f"[Skipped] {account['email']} window already exists")
```

### Window Synchronization

**Function**: Synchronize window information between database and BitBrowser

```python
async def sync_browser_windows():
    """Synchronize window information"""

    # 1. Get BitBrowser window list
    browsers = get_browser_list()

    # 2. Update window information in database
    for browser in browsers:
        # Extract email from remark
        email = extract_email_from_remark(browser['remark'])
        if email:
            update_account_browser_id(email, browser['id'])

    # 3. Clean deleted windows
    all_browser_ids = {b['id'] for b in browsers}
    accounts = get_all_accounts()

    for account in accounts:
        if account.get('browser_id') and account['browser_id'] not in all_browser_ids:
            # Window was deleted, clear browser_id
            update_account_browser_id(account['email'], None)
```

## Proxy Configuration

### Proxy Types

| proxyMethod | Description |
|-------------|-------------|
| 1 | No proxy |
| 2 | Custom proxy |
| 3 | Extract IP |

### Proxy Format

**Socks5**:
```
socks5://username:password@host:port
```

**HTTP**:
```
http://username:password@host:port
```

### Parse Proxy

```python
def parse_proxy(proxy_url):
    """Parse proxy URL"""
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

    # socks5://host:port (no authentication)
    match = re.match(r'(\w+)://([^:]+):(\d+)', proxy_url)
    if match:
        return {
            "proxyType": match.group(1),
            "host": match.group(2),
            "port": match.group(3)
        }

    return None
```

### Proxy Assignment

```python
def assign_proxies(accounts, proxies):
    """Assign proxies to accounts"""
    proxy_index = 0

    for account in accounts:
        if proxy_index < len(proxies):
            proxy = parse_proxy(proxies[proxy_index])
            account['proxy'] = proxy
            proxy_index += 1
        else:
            # Not enough proxies, cycle through
            proxy_index = 0

    return accounts
```

## 2FA Secret Key Management

### Sync 2FA to Browser

**Script**: `sync_2fa_to_browser.py`

```python
async def sync_2fa_to_browser(email):
    """Sync 2FA secret key to browser configuration"""

    # 1. Get account info from database
    account = get_account(email)
    if not account or not account.get('fa_secret'):
        return False, "Account not found or 2FA not set"

    # 2. Get browser ID
    browser_id = account.get('browser_id')
    if not browser_id:
        return False, "Account not associated with browser window"

    # 3. Update browser configuration
    response = requests.post(
        'http://127.0.0.1:54345/browser/update',
        json={
            "id": browser_id,
            "faSecretKey": account['fa_secret']
        },
        proxies={'http': None, 'https': None}
    )

    if response.json().get('success'):
        return True, "2FA secret key synced"
    else:
        return False, "Sync failed"
```

### Batch Sync

```python
async def batch_sync_2fa():
    """Batch sync 2FA secret keys for all accounts"""

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

## Playwright Integration

### Connect to Browser

```python
from playwright.async_api import async_playwright

async def connect_to_browser(browser_id):
    """Connect to BitBrowser window via CDP"""

    # 1. Open browser window
    response = requests.post(
        'http://127.0.0.1:54345/browser/open',
        json={"id": browser_id},
        proxies={'http': None, 'https': None}
    )

    # 2. Get WebSocket endpoint
    ws_endpoint = response.json()['data']['ws']

    # 3. Connect Playwright
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(ws_endpoint)
        context = browser.contexts[0]  # Use existing context
        page = context.pages[0] if context.pages else await context.new_page()

        return browser, page
```

### Execute Automation Task

```python
async def execute_automation(browser_id, task_func):
    """Execute automation task in browser"""

    try:
        # Connect to browser
        browser, page = await connect_to_browser(browser_id)

        # Execute task
        result = await task_func(page)

        # Close connection (don't close browser window)
        await browser.close()

        return result

    except Exception as e:
        logger.error(f"Automation task failed: {e}")
        return False, str(e)
```

## Window Lifecycle

### Create Window

```
1. Prepare configuration (account, proxy, 2FA)
   ↓
2. Call /browser/update API
   ↓
3. Get window ID
   ↓
4. Save to database
```

### Use Window

```
1. Get browser_id from database
   ↓
2. Call /browser/open API
   ↓
3. Get WebSocket endpoint
   ↓
4. Playwright connection
   ↓
5. Execute automation task
   ↓
6. Disconnect Playwright connection
```

### Delete Window

```
1. Call /browser/close API (optional)
   ↓
2. Call /browser/delete API
   ↓
3. Clear browser_id from database
```

## Window Configuration

### Complete Configuration Example

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

### Fingerprint Configuration

BitBrowser automatically generates fingerprint configuration, including:

- User-Agent
- Screen resolution
- Timezone
- Language
- WebRTC
- Canvas fingerprint
- WebGL fingerprint

## Best Practices

1. **Window Naming**: Use email as window name for easy identification
2. **Remark Information**: Record account status and key information in remarks
3. **Proxy Configuration**: Use independent proxy for each account to avoid association
4. **2FA Sync**: Sync to browser immediately after setting 2FA
5. **Regular Cleanup**: Delete unused windows
6. **Window Reuse**: Keep windows open after task completion for next use
7. **Error Handling**: Catch API call exceptions, log detailed information

## Troubleshooting

### Window Open Failed

**Causes**:
- BitBrowser not started
- Window ID doesn't exist
- Port occupied

**Solutions**:
```python
# Check if BitBrowser is running
response = requests.get('http://127.0.0.1:54345/browser/list')
if response.status_code != 200:
    print("BitBrowser not started")
```

### Playwright Connection Failed

**Causes**:
- WebSocket endpoint error
- Browser already closed
- Network issues

**Solutions**:
```python
# Retry connection
for attempt in range(3):
    try:
        browser = await p.chromium.connect_over_cdp(ws_endpoint)
        break
    except Exception as e:
        if attempt == 2:
            raise
        await asyncio.sleep(2)
```

### Proxy Not Working

**Causes**:
- Proxy configuration error
- Proxy server unavailable
- Proxy authentication failed

**Solutions**:
1. Check if proxy format is correct
2. Test proxy connection
3. Verify proxy credentials

## API Wrapper

### bit_api.py

```python
import requests

BASE_URL = "http://127.0.0.1:54345"
PROXIES = {'http': None, 'https': None}

def create_or_update_browser(config):
    """Create or update browser window"""
    response = requests.post(
        f"{BASE_URL}/browser/update",
        json=config,
        proxies=PROXIES
    )
    return response.json()

def open_browser(browser_id):
    """Open browser window"""
    response = requests.post(
        f"{BASE_URL}/browser/open",
        json={"id": browser_id},
        proxies=PROXIES
    )
    return response.json()

def close_browser(browser_id):
    """Close browser window"""
    response = requests.post(
        f"{BASE_URL}/browser/close",
        json={"id": browser_id},
        proxies=PROXIES
    )
    return response.json()

def delete_browsers(browser_ids):
    """Delete browser windows"""
    response = requests.post(
        f"{BASE_URL}/browser/delete",
        json={"ids": browser_ids},
        proxies=PROXIES
    )
    return response.json()

def get_browser_list(page=0, page_size=100):
    """Get browser window list"""
    response = requests.post(
        f"{BASE_URL}/browser/list",
        json={"page": page, "pageSize": page_size},
        proxies=PROXIES
    )
    return response.json()
```

## Performance Optimization

### Browser Pool

```python
class BrowserPool:
    """Browser window pool"""

    def __init__(self, max_size=10):
        self.max_size = max_size
        self.pool = {}  # browser_id -> ws_endpoint

    async def get_browser(self, browser_id):
        """Get browser connection"""
        if browser_id in self.pool:
            return self.pool[browser_id]

        # Open new window
        ws_endpoint = await open_browser(browser_id)
        self.pool[browser_id] = ws_endpoint

        # Limit pool size
        if len(self.pool) > self.max_size:
            # Close oldest window
            oldest_id = next(iter(self.pool))
            await close_browser(oldest_id)
            del self.pool[oldest_id]

        return ws_endpoint

    async def close_all(self):
        """Close all windows"""
        for browser_id in self.pool:
            await close_browser(browser_id)
        self.pool.clear()
```

### Batch Operations

```python
async def batch_create_browsers(accounts, batch_size=10):
    """Batch create browser windows"""

    for i in range(0, len(accounts), batch_size):
        batch = accounts[i:i + batch_size]

        # Create concurrently
        tasks = [create_browser_window(acc) for acc in batch]
        results = await asyncio.gather(*tasks)

        # Wait to avoid API rate limiting
        await asyncio.sleep(1)

    return results
```
