# 数据库设计

## 概述

Auto BitBrowser 使用 **SQLite** 作为数据存储，通过 `DBManager` 类提供线程安全的数据库操作。数据库文件默认为 `accounts.db`，位于项目根目录。

## 数据库管理器

### DBManager 类

位置: `database.py`

**核心功能**:
- 线程安全的数据库连接管理
- 自动创建表结构
- 从文本文件导入数据
- 支持上下文管理器

**使用示例**:
```python
from database import DBManager

# 使用上下文管理器
with DBManager.get_db() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM accounts WHERE email = ?", (email,))
    result = cursor.fetchone()
```

## 表结构

### accounts 表

存储 Google 账号信息及其状态。

**字段定义**:

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| email | TEXT | PRIMARY KEY | 账号邮箱（唯一标识） |
| password | TEXT | | 账号密码 |
| backup_email | TEXT | | 辅助邮箱（可选） |
| fa_secret | TEXT | | 2FA 密钥（TOTP Secret） |
| browser_id | TEXT | | BitBrowser 窗口 ID |
| status | TEXT | DEFAULT 'pending' | 账号状态 |
| sheer_link | TEXT | | SheerID 验证链接 |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 更新时间 |

**创建语句**:
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

**索引**:
```sql
CREATE INDEX IF NOT EXISTS idx_status ON accounts(status);
CREATE INDEX IF NOT EXISTS idx_browser_id ON accounts(browser_id);
```

### 账号状态 (status)

| 状态值 | 说明 | 触发条件 |
|--------|------|----------|
| `pending` | 待处理 | 初始状态 |
| `link_ready` | 有资格待验证 | 获取到 SheerID 链接 |
| `verified` | 已验证未绑卡 | SheerID 验证通过 |
| `subscribed` | 已绑卡订阅 | 完成绑卡流程 |
| `ineligible` | 无资格 | 检测到不符合条件 |
| `error` | 错误 | 任务执行失败 |

**状态流转图**:
```
pending
  ↓
link_ready (获取 SheerID 链接)
  ↓
verified (验证通过)
  ↓
subscribed (绑卡成功)

任何状态 → error (发生错误)
任何状态 → ineligible (检测到无资格)
```

### config 表

存储系统配置信息（Key-Value 结构）。

**字段定义**:

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| key | TEXT | PRIMARY KEY | 配置键 |
| value | TEXT | | 配置值 |

**创建语句**:
```sql
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT
)
```

**配置项**:

| Key | 说明 | 示例值 |
|-----|------|--------|
| `sheerid_api_key` | SheerID API 密钥 | `cdk_xxx...` |
| `card_number` | 虚拟卡号 | `5481087170529907` |
| `card_exp_month` | 卡过期月份 | `01` |
| `card_exp_year` | 卡过期年份 | `32` |
| `card_cvv` | 卡 CVV | `536` |
| `card_zip` | 卡邮编 | `10001` |

## 数据操作

### 账号管理

#### 1. 创建账号

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

#### 2. 查询账号

```python
def get_account(email: str):
    with DBManager.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM accounts WHERE email = ?", (email,))
        return cursor.fetchone()
```

#### 3. 更新账号状态

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

#### 4. 批量查询

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

### 配置管理

#### 1. 获取配置

```python
def get_config(key: str) -> str:
    with DBManager.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else ""
```

#### 2. 设置配置

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

## 数据导入

### 从文本文件导入

`DBManager` 提供了从 `accounts.txt` 导入数据的功能：

```python
DBManager.import_from_files()
```

**导入逻辑**:
1. 读取 `accounts.txt` 文件
2. 解析分隔符配置（支持 `----`, `---`, `|`, `,` 等）
3. 按行解析账号信息
4. 使用 `INSERT OR REPLACE` 插入数据库
5. 保留现有的 `browser_id`, `status`, `sheer_link` 字段

**文件格式**:
```text
分隔符="----"
email1@gmail.com----password1----backup1@email.com----ABCD1234EFGH5678
email2@gmail.com----password2----backup2@email.com----WXYZ9012STUV3456
```

## 数据导出

### 导出为文本文件

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

## 数据迁移

### 从旧版本迁移

如果你有旧版本的文本文件数据，可以使用 `migrate_txt_to_db.py` 脚本：

```bash
python migrate_txt_to_db.py
```

**迁移步骤**:
1. 读取所有 `.txt` 文件（`accounts.txt`, `已绑卡号.txt` 等）
2. 解析账号信息
3. 根据文件名推断账号状态
4. 导入到数据库

## 数据备份

### 备份数据库

```bash
# 简单备份
cp accounts.db accounts.db.backup

# 带时间戳的备份
cp accounts.db accounts.db.$(date +%Y%m%d_%H%M%S)
```

### 恢复数据库

```bash
cp accounts.db.backup accounts.db
```

### 导出为 SQL

```bash
sqlite3 accounts.db .dump > backup.sql
```

### 从 SQL 恢复

```bash
sqlite3 accounts.db < backup.sql
```

## 性能优化

### 索引优化

为常用查询字段创建索引：

```sql
-- 状态查询索引
CREATE INDEX IF NOT EXISTS idx_status ON accounts(status);

-- 浏览器 ID 查询索引
CREATE INDEX IF NOT EXISTS idx_browser_id ON accounts(browser_id);

-- 更新时间索引（用于排序）
CREATE INDEX IF NOT EXISTS idx_updated_at ON accounts(updated_at DESC);
```

### 批量操作

使用事务批量插入数据：

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

### 连接池

SQLite 不支持真正的连接池，但 `DBManager` 使用线程本地存储确保线程安全：

```python
import threading

_thread_local = threading.local()

def get_db():
    if not hasattr(_thread_local, 'conn'):
        _thread_local.conn = sqlite3.connect('accounts.db')
    return _thread_local.conn
```

## 数据一致性

### 事务管理

所有写操作都在事务中执行：

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

### 并发控制

使用线程锁保护关键操作：

```python
import threading

_db_lock = threading.Lock()

def update_account_safe(email: str, **kwargs):
    with _db_lock:
        with DBManager.get_db() as conn:
            # 数据库操作
            pass
```

## 数据清理

### 清理错误账号

```sql
DELETE FROM accounts WHERE status = 'error';
```

### 重置账号状态

```sql
UPDATE accounts SET status = 'pending' WHERE status = 'error';
```

### 清理无效数据

```sql
-- 删除没有密码的账号
DELETE FROM accounts WHERE password IS NULL OR password = '';

-- 删除重复账号（保留最新的）
DELETE FROM accounts
WHERE rowid NOT IN (
    SELECT MAX(rowid)
    FROM accounts
    GROUP BY email
);
```

## 数据统计

### 账号状态统计

```sql
SELECT status, COUNT(*) as count
FROM accounts
GROUP BY status;
```

### 浏览器窗口统计

```sql
SELECT
    COUNT(*) as total,
    COUNT(browser_id) as with_browser,
    COUNT(*) - COUNT(browser_id) as without_browser
FROM accounts;
```

### 2FA 覆盖率

```sql
SELECT
    COUNT(*) as total,
    COUNT(fa_secret) as with_2fa,
    ROUND(COUNT(fa_secret) * 100.0 / COUNT(*), 2) as coverage_percent
FROM accounts;
```

## 故障排查

### 数据库锁定

如果遇到 "database is locked" 错误：

```python
# 增加超时时间
conn = sqlite3.connect('accounts.db', timeout=30.0)
```

### 数据库损坏

检查数据库完整性：

```bash
sqlite3 accounts.db "PRAGMA integrity_check;"
```

修复数据库：

```bash
sqlite3 accounts.db ".recover" | sqlite3 accounts_recovered.db
```

### 查看表结构

```bash
sqlite3 accounts.db ".schema accounts"
```

### 查看数据库大小

```bash
ls -lh accounts.db
```

## 最佳实践

1. **定期备份**: 每天自动备份数据库
2. **使用事务**: 批量操作使用事务
3. **索引优化**: 为常用查询创建索引
4. **数据验证**: 插入前验证数据格式
5. **错误处理**: 捕获并记录数据库异常
6. **连接管理**: 使用上下文管理器自动关闭连接
7. **并发控制**: 写操作使用锁保护
8. **数据清理**: 定期清理无效数据
