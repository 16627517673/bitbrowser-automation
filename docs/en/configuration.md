# Configuration Guide

## Overview

Auto BitBrowser supports multiple configuration methods, including text files, database configuration, and environment variables. This document details all configuration options.

## Configuration Priority

```
Database Configuration > Environment Variables > Text Files > Default Values
```

## Account Configuration

### accounts.txt

Account information configuration file, supports multiple delimiters.

#### Delimiter Configuration

Configure the delimiter in the **first line** of the file:

```text
分隔符="----"
```

Supported delimiters:

| Delimiter | Description | Recommendation |
|-----------|-------------|----------------|
| `----` | Four hyphens | ⭐⭐⭐⭐⭐ Most recommended |
| `---` | Three hyphens | ⭐⭐⭐⭐ |
| `\|` | Pipe | ⭐⭐⭐ |
| `,` | Comma | ⭐⭐ Password cannot contain commas |
| `;` | Semicolon | ⭐⭐ |
| `\t` | Tab | ⭐ |

#### Account Format

```
Email[Delimiter]Password[Delimiter]Backup Email[Delimiter]2FA Secret
```

**Field Description**:

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| Email | ✅ | Google account email | `user@gmail.com` |
| Password | ✅ | Account password | `MyP@ssw0rd!` |
| Backup Email | ❌ | Backup email (optional) | `backup@email.com` |
| 2FA Secret | ❌ | TOTP secret (optional) | `ABCD1234EFGH5678` |

#### Examples

**Complete Format**:
```text
分隔符="----"
user1@gmail.com----MyPassword123----backup1@email.com----ABCD1234EFGH5678
user2@gmail.com----P@ssw0rd!%%99----backup2@email.com----WXYZ9012STUV3456
```

**Minimal Format** (email and password only):
```text
分隔符="----"
user1@gmail.com----MyPassword123
user2@gmail.com----P@ssw0rd!%%99
```

**With 2FA, No Backup Email**:
```text
分隔符="----"
user1@gmail.com----MyPassword123----ABCD1234EFGH5678
user2@gmail.com----P@ssw0rd!%%99----WXYZ9012STUV3456
```

#### Notes

1. **Password Special Characters**: Supports all special characters (`@#$%^&*` etc.)
2. **Empty Lines**: Automatically ignored
3. **Comments**: Lines starting with `#` are ignored
4. **Field Order**: Must follow `Email-Password-Backup Email-2FA` order
5. **Delimiter Consistency**: One file can only use one delimiter

#### Import to Database

**Method 1: Via Web Interface**

1. Visit http://localhost:5173/accounts
2. Click "Import Accounts" button
3. Select `accounts.txt` file
4. Click "Confirm Import"

**Method 2: Automatic Import**

The program automatically detects `accounts.txt` and imports to database on startup.

## Proxy Configuration

### proxies.txt

Proxy IP configuration file, one proxy per line.

#### Format

**Socks5 Proxy**:
```text
socks5://username:password@host:port
```

**HTTP Proxy**:
```text
http://username:password@host:port
```

**No Authentication Proxy**:
```text
socks5://host:port
http://host:port
```

#### Example

```text
socks5://user1:pass1@proxy1.example.com:1080
socks5://user2:pass2@proxy2.example.com:1080
http://user3:pass3@proxy3.example.com:8080
```

#### Proxy Assignment

Proxies are assigned to accounts in order:

```
Account 1 -> Proxy 1
Account 2 -> Proxy 2
Account 3 -> Proxy 3
Account 4 -> Proxy 1  # Cycle through
```

#### Notes

1. **Proxy Count**: Recommended proxy count ≥ account count
2. **Proxy Quality**: Use stable residential or datacenter proxies
3. **Proxy Region**: Recommended to use proxies from same region as account registration
4. **Proxy Testing**: Test proxies before use

## Virtual Card Configuration

### cards.txt

Virtual card information configuration file, used for age verification and card binding.

#### Format

```
Card Number Month Year CVV
```

Fields are separated by **spaces**.

#### Field Description

| Field | Description | Format | Example |
|-------|-------------|--------|---------|
| Card Number | 13-19 digits | Numbers only | `5481087170529907` |
| Month | Expiration month | 01-12 | `01` |
| Year | Last two digits of expiration year | YY | `32` (2032) |
| CVV | Security code | 3-4 digits | `536` |

#### Example

```text
5481087170529907 01 32 536
5481087143137903 12 28 749
4532123456789012 06 30 123
```

#### Notes

1. **Virtual Cards**: Recommended to use virtual cards to avoid real card information leakage
2. **Card Status**: Ensure card is valid and has balance
3. **Card Region**: Use cards matching account region
4. **Security**: Do not commit real card numbers to Git repository

#### Recommended Virtual Card Services

- **HolyCard**: https://www.holy-card.com/
  - Supports Gemini subscription, GPT Team, $0 Plus
  - Prices as low as 2 yuan/card

## Database Configuration

### config Table

System configuration is stored in the database `config` table.

#### Configuration Items

| Key | Description | Example Value |
|-----|-------------|---------------|
| `sheerid_api_key` | SheerID API key | `cdk_xxx...` |
| `card_number` | Virtual card number | `5481087170529907` |
| `card_exp_month` | Card expiration month | `01` |
| `card_exp_year` | Card expiration year | `32` |
| `card_cvv` | Card CVV | `536` |
| `card_zip` | Card ZIP code | `10001` |

#### Configure via Web Interface

1. Visit http://localhost:5173/tasks
2. Click "⚙️ Config" button
3. Fill in configuration information
4. Click "Save"

#### Configure via API

```bash
curl -X PUT http://localhost:8000/config \
  -H "Content-Type: application/json" \
  -d '{
    "sheerid_api_key": "your_api_key",
    "card_number": "5481087170529907",
    "card_exp_month": "01",
    "card_exp_year": "32",
    "card_cvv": "536",
    "card_zip": "10001"
  }'
```

## Environment Variables

### Supported Environment Variables

| Variable Name | Description | Default Value |
|---------------|-------------|---------------|
| `CARD_NUMBER` | Virtual card number | - |
| `CARD_CVV` | Card CVV | - |
| `CARD_EXP_MONTH` | Card expiration month | - |
| `CARD_EXP_YEAR` | Card expiration year | - |
| `CARD_ZIP` | Card ZIP code | - |
| `SHEERID_API_KEY` | SheerID API Key | - |

### Setting Environment Variables

**Linux/macOS**:
```bash
export CARD_NUMBER="5481087170529907"
export CARD_CVV="536"
export CARD_EXP_MONTH="01"
export CARD_EXP_YEAR="32"
export CARD_ZIP="10001"
```

**Windows**:
```cmd
set CARD_NUMBER=5481087170529907
set CARD_CVV=536
set CARD_EXP_MONTH=01
set CARD_EXP_YEAR=32
set CARD_ZIP=10001
```

### .env File

Create `.env` file (already in `.gitignore`):

```bash
CARD_NUMBER=5481087170529907
CARD_CVV=536
CARD_EXP_MONTH=01
CARD_EXP_YEAR=32
CARD_ZIP=10001
SHEERID_API_KEY=your_api_key
```

## BitBrowser Configuration

### API Address

Default: `http://127.0.0.1:54345`

If BitBrowser uses a different port, modify `BASE_URL` in the code.

### Window Configuration

Configure default window parameters in `create_window.py`:

```python
DEFAULT_CONFIG = {
    "proxyMethod": 2,  # 2=custom proxy, 3=no proxy
    "proxyType": "socks5",  # socks5 or http
    "fingerprint": {
        "language": "en-US",
        "timezone": "America/New_York",
        "webrtc": "disabled"
    }
}
```

## Task Configuration

### Concurrency Level

Controls the number of simultaneously running browsers.

**Recommended Values**:
- 8GB RAM: 1-2
- 16GB RAM: 2-3
- 32GB RAM: 3-5

**Configuration Methods**:
- Web Interface: "Concurrency" slider on task page
- API: `concurrency` parameter

### Task Timeout

Configure in `web/backend/routers/tasks.py`:

```python
TASK_TIMEOUT = 300  # 5 minutes
```

### Close Browser

Whether to close browser window after task completion.

**Configuration Methods**:
- Web Interface: "Close After" checkbox
- API: `close_after` parameter

## Logging Configuration

### Log Level

Configure in `web/backend/main.py`:

```python
import logging

logging.basicConfig(
    level=logging.INFO,  # DEBUG, INFO, WARNING, ERROR
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### Log File

Output logs to file:

```python
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
```

## Database Configuration

### Database Path

Default: `accounts.db` (project root directory)

Modify path:

```python
# database.py
DB_PATH = "/path/to/your/database.db"
```

### Database Backup

Regular database backup:

```bash
# Manual backup
cp accounts.db accounts.db.backup

# Automatic backup (cron)
0 2 * * * cp /path/to/accounts.db /path/to/backups/accounts.db.$(date +\%Y\%m\%d)
```

## Frontend Configuration

### API Address

Configure in `web/frontend/src/api/index.js`:

```javascript
const API_BASE_URL = 'http://localhost:8000'
const WS_BASE_URL = 'ws://localhost:8000'
```

### Port Configuration

Configure in `web/frontend/vite.config.js`:

```javascript
export default defineConfig({
  server: {
    port: 5173,  // Frontend port
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
```

## Security Configuration

### Sensitive File Protection

Ensure the following files are in `.gitignore`:

```gitignore
accounts.txt
cards.txt
proxies.txt
*.db
.env
.env.local
```

### Data Encryption

Recommended to encrypt sensitive configuration files:

```bash
# Encrypt using GPG
gpg -c accounts.txt

# Decrypt
gpg accounts.txt.gpg
```

### Access Control

Backend only listens on `localhost`, not exposed externally:

```python
# web/backend/main.py
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
```

## Configuration Validation

### Check Configuration

```bash
# Check account configuration
python -c "from database import DBManager; print(DBManager.get_account_count())"

# Check BitBrowser connection
curl http://127.0.0.1:54345/browser/list

# Check backend API
curl http://localhost:8000/accounts
```

### Configuration Testing

```python
# test_config.py
from database import DBManager
from web.backend.routers.config import get_config

# Test database
print(f"Account count: {DBManager.get_account_count()}")

# Test configuration
print(f"SheerID API Key: {get_config('sheerid_api_key')}")
print(f"Card number: {get_config('card_number')}")
```

## Configuration Best Practices

1. **Separate Sensitive Information**: Use environment variables or database configuration, don't hardcode
2. **Regular Backups**: Backup database and configuration files daily
3. **Version Control**: Don't commit sensitive files to Git
4. **Encrypted Storage**: Encrypt sensitive configuration files
5. **Permission Control**: Limit access permissions to configuration files
6. **Configuration Validation**: Validate configuration before startup
7. **Documentation Updates**: Update documentation when configuration changes

## Troubleshooting

### Configuration File Read Failed

**Causes**:
- File does not exist
- File format error
- Encoding issues

**Solutions**:
```bash
# Check if file exists
ls -la accounts.txt

# Check file encoding
file accounts.txt

# Convert encoding
iconv -f GBK -t UTF-8 accounts.txt > accounts_utf8.txt
```

### Database Configuration Not Taking Effect

**Causes**:
- Configuration not saved
- Cache issues
- Database locked

**Solutions**:
```python
# Clear cache
from web.backend.routers.config import get_config
get_config.cache_clear()

# Restart service
```

### Environment Variables Not Taking Effect

**Causes**:
- Virtual environment not activated
- Environment variables not exported
- Variable name error

**Solutions**:
```bash
# Check environment variables
echo $CARD_NUMBER

# Re-export
export CARD_NUMBER="5481087170529907"

# Restart service
```
