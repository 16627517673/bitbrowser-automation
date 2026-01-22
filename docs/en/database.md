# Database Design

## Overview

Auto BitBrowser uses **SQLite** for data storage, providing thread-safe database operations through the `DBManager` class. The database file defaults to `accounts.db`, located in the project root directory.

## Database Manager

### DBManager Class

Location: `database.py`

**Core Features**:
- Thread-safe database connection management
- Automatic table structure creation
- Import data from text files
- Context manager support

**Usage Example**:
```python
from database import DBManager

# Using context manager
with DBManager.get_db() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM accounts WHERE email = ?", (email,))
    result = cursor.fetchone()
```

## Table Structure

### accounts Table

Stores Google account information and status.

**Field Definitions**:

| Field Name | Type | Constraints | Description |
|------------|------|-------------|-------------|
| email | TEXT | PRIMARY KEY | Account email (unique identifier) |
| password | TEXT | | Account password |
| backup_email | TEXT | | Backup email (optional) |
| fa_secret | TEXT | | 2FA secret key (TOTP Secret) |
| browser_id | TEXT | | BitBrowser window ID |
| status | TEXT | DEFAULT 'pending' | Account status |
| sheer_link | TEXT | | SheerID verification link |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Update time |

**Creation Statement**:
```sql
CREATE TABLE IF NOT EXISTS accounts (
    email TEXT PRIMARY KEY,
    password TEXT,
    backup_email TEXT,
    fa_secret TEXT,
    browser_id TEXT,
    status TEXT DEFAULT 'pending',
    sheer_link TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**Indexes**:
```sql
CREATE INDEX IF NOT EXISTS idx_status ON accounts(status);
CREATE INDEX IF NOT EXISTS idx_browser_id ON accounts(browser_id);
```

### Account Status (status)

| Status Value | Description | Trigger Condition |
|--------------|-------------|-------------------|
| `pending` | Pending | Initial state |
| `link_ready` | Eligible, pending verification | SheerID link obtained |
| `verified` | Verified, card not bound | SheerID verification passed |
| `subscribed` | Card bound and subscribed | Card binding completed |
| `ineligible` | Ineligible | Detected as not meeting requirements |
| `error` | Error | Task execution failed |

**Status Flow Diagram**:
```
pending
  ↓
link_ready (Get SheerID link)
  ↓
verified (Verification passed)
  ↓
subscribed (Card binding successful)

Any status → error (Error occurred)
Any status → ineligible (Detected as ineligible)
```

### config Table

Stores system configuration information (Key-Value structure).

**Field Definitions**:

| Field Name | Type | Constraints | Description |
|------------|------|-------------|-------------|
| key | TEXT | PRIMARY KEY | Configuration key |
| value | TEXT | | Configuration value |

**Creation Statement**:
```sql
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT
)
```

**Configuration Items**:

| Key | Description | Example Value |
|-----|-------------|---------------|
| `sheerid_api_key` | SheerID API key | `cdk_xxx...` |
| `card_number` | Virtual card number | `5481087170529907` |
| `card_exp_month` | Card expiration month | `01` |
| `card_exp_year` | Card expiration year | `32` |
| `card_cvv` | Card CVV | `536` |
| `card_zip` | Card ZIP code | `10001` |

## Data Operations

### Account Management

#### 1. Create Account

```python
def add_account(email: str, password: str, backup_email: str = "", fa_secret: str = ""):
    with DBManager.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO accounts
            (email, password, backup_email, fa_secret, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (email, password, backup_email, fa_secret))
        conn.commit()
```

#### 2. Query Account

```python
def get_account(email: str):
    with DBManager.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM accounts WHERE email = ?", (email,))
        return cursor.fetchone()
```

#### 3. Update Account Status

```python
def update_status(email: str, status: str):
    with DBManager.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE accounts
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE email = ?
        """, (status, email))
        conn.commit()
```

#### 4. Batch Query

```python
def list_accounts(status: str = None, page: int = 1, page_size: int = 50):
    offset = (page - 1) * page_size
    with DBManager.get_db() as conn:
        cursor = conn.cursor()
        if status:
            cursor.execute("""
                SELECT * FROM accounts
                WHERE status = ?
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
            """, (status, page_size, offset))
        else:
            cursor.execute("""
                SELECT * FROM accounts
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
            """, (page_size, offset))
        return cursor.fetchall()
```

### Configuration Management

#### 1. Get Configuration

```python
def get_config(key: str) -> str:
    with DBManager.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else ""
```

#### 2. Set Configuration

```python
def set_config(key: str, value: str):
    with DBManager.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO config (key, value)
            VALUES (?, ?)
        """, (key, value))
        conn.commit()
```

## Data Import

### Import from Text File

`DBManager` provides functionality to import data from `accounts.txt`:

```python
DBManager.import_from_files()
```

**Import Logic**:
1. Read `accounts.txt` file
2. Parse delimiter configuration (supports `----`, `---`, `|`, `,`, etc.)
3. Parse account information line by line
4. Insert into database using `INSERT OR REPLACE`
5. Preserve existing `browser_id`, `status`, `sheer_link` fields

**File Format**:
```text
分隔符="----"
email1@gmail.com----password1----backup1@email.com----ABCD1234EFGH5678
email2@gmail.com----password2----backup2@email.com----WXYZ9012STUV3456
```

## Data Export

### Export to Text File

```python
def export_accounts(status: str = None) -> str:
    accounts = list_accounts(status=status)
    lines = []
    for acc in accounts:
        line = f"{acc['email']}----{acc['password']}"
        if acc['backup_email']:
            line += f"----{acc['backup_email']}"
        if acc['fa_secret']:
            line += f"----{acc['fa_secret']}"
        lines.append(line)
    return "\n".join(lines)
```

## Data Migration

### Migrate from Old Version

If you have text file data from an old version, use the `migrate_txt_to_db.py` script:

```bash
python migrate_txt_to_db.py
```

**Migration Steps**:
1. Read all `.txt` files (`accounts.txt`, `已绑卡号.txt`, etc.)
2. Parse account information
3. Infer account status from filename
4. Import to database

## Data Backup

### Backup Database

```bash
# Simple backup
cp accounts.db accounts.db.backup

# Backup with timestamp
cp accounts.db accounts.db.$(date +%Y%m%d_%H%M%S)
```

### Restore Database

```bash
cp accounts.db.backup accounts.db
```

### Export as SQL

```bash
sqlite3 accounts.db .dump > backup.sql
```

### Restore from SQL

```bash
sqlite3 accounts.db < backup.sql
```

## Performance Optimization

### Index Optimization

Create indexes for frequently queried fields:

```sql
-- Status query index
CREATE INDEX IF NOT EXISTS idx_status ON accounts(status);

-- Browser ID query index
CREATE INDEX IF NOT EXISTS idx_browser_id ON accounts(browser_id);

-- Update time index (for sorting)
CREATE INDEX IF NOT EXISTS idx_updated_at ON accounts(updated_at DESC);
```

### Batch Operations

Use transactions for batch inserts:

```python
def batch_insert(accounts: list):
    with DBManager.get_db() as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT OR REPLACE INTO accounts
            (email, password, backup_email, fa_secret)
            VALUES (?, ?, ?, ?)
        """, accounts)
        conn.commit()
```

### Connection Pool

SQLite doesn't support true connection pooling, but `DBManager` uses thread-local storage to ensure thread safety:

```python
import threading

_thread_local = threading.local()

def get_db():
    if not hasattr(_thread_local, 'conn'):
        _thread_local.conn = sqlite3.connect('accounts.db')
    return _thread_local.conn
```

## Data Consistency

### Transaction Management

All write operations are executed within transactions:

```python
with DBManager.get_db() as conn:
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE accounts SET status = ? WHERE email = ?", ...)
        cursor.execute("INSERT INTO config VALUES (?, ?)", ...)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
```

### Concurrency Control

Use thread locks to protect critical operations:

```python
import threading

_db_lock = threading.Lock()

def update_account_safe(email: str, **kwargs):
    with _db_lock:
        with DBManager.get_db() as conn:
            # Database operations
            pass
```

## Data Cleanup

### Clean Error Accounts

```sql
DELETE FROM accounts WHERE status = 'error';
```

### Reset Account Status

```sql
UPDATE accounts SET status = 'pending' WHERE status = 'error';
```

### Clean Invalid Data

```sql
-- Delete accounts without password
DELETE FROM accounts WHERE password IS NULL OR password = '';

-- Delete duplicate accounts (keep latest)
DELETE FROM accounts
WHERE rowid NOT IN (
    SELECT MAX(rowid)
    FROM accounts
    GROUP BY email
);
```

## Data Statistics

### Account Status Statistics

```sql
SELECT status, COUNT(*) as count
FROM accounts
GROUP BY status;
```

### Browser Window Statistics

```sql
SELECT
    COUNT(*) as total,
    COUNT(browser_id) as with_browser,
    COUNT(*) - COUNT(browser_id) as without_browser
FROM accounts;
```

### 2FA Coverage

```sql
SELECT
    COUNT(*) as total,
    COUNT(fa_secret) as with_2fa,
    ROUND(COUNT(fa_secret) * 100.0 / COUNT(*), 2) as coverage_percent
FROM accounts;
```

## Troubleshooting

### Database Locked

If you encounter "database is locked" error:

```python
# Increase timeout
conn = sqlite3.connect('accounts.db', timeout=30.0)
```

### Database Corruption

Check database integrity:

```bash
sqlite3 accounts.db "PRAGMA integrity_check;"
```

Repair database:

```bash
sqlite3 accounts.db ".recover" | sqlite3 accounts_recovered.db
```

### View Table Structure

```bash
sqlite3 accounts.db ".schema accounts"
```

### View Database Size

```bash
ls -lh accounts.db
```

## Best Practices

1. **Regular Backups**: Automatically backup database daily
2. **Use Transactions**: Use transactions for batch operations
3. **Index Optimization**: Create indexes for frequently used queries
4. **Data Validation**: Validate data format before insertion
5. **Error Handling**: Catch and log database exceptions
6. **Connection Management**: Use context managers to automatically close connections
7. **Concurrency Control**: Use locks to protect write operations
8. **Data Cleanup**: Regularly clean invalid data
