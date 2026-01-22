# 配置指南

## 概述

Auto BitBrowser 支持多种配置方式，包括文本文件、数据库配置和环境变量。本文档详细说明各种配置选项。

## 配置优先级

```
数据库配置 > 环境变量 > 文本文件 > 默认值
```

## 账号配置

### accounts.txt

账号信息配置文件，支持多种分隔符。

#### 分隔符配置

在文件**第一行**配置分隔符：

```text
分隔符="----"
```

支持的分隔符：

| 分隔符 | 说明 | 推荐度 |
|--------|------|--------|
| `----` | 四短横线 | ⭐⭐⭐⭐⭐ 最推荐 |
| `---` | 三短横线 | ⭐⭐⭐⭐ |
| `\|` | 竖线 | ⭐⭐⭐ |
| `,` | 逗号 | ⭐⭐ 密码中不能有逗号 |
| `;` | 分号 | ⭐⭐ |
| `\t` | Tab 键 | ⭐ |

#### 账号格式

```
邮箱[分隔符]密码[分隔符]辅助邮箱[分隔符]2FA密钥
```

**字段说明**:

| 字段 | 必填 | 说明 | 示例 |
|------|------|------|------|
| 邮箱 | ✅ | Google 账号邮箱 | `user@gmail.com` |
| 密码 | ✅ | 账号密码 | `MyP@ssw0rd!` |
| 辅助邮箱 | ❌ | 辅助邮箱（可选） | `backup@email.com` |
| 2FA密钥 | ❌ | TOTP 密钥（可选） | `ABCD1234EFGH5678` |

#### 示例

**完整格式**:
```text
分隔符="----"
user1@gmail.com----MyPassword123----backup1@email.com----ABCD1234EFGH5678
user2@gmail.com----P@ssw0rd!%%99----backup2@email.com----WXYZ9012STUV3456
```

**最简格式**（只有邮箱和密码）:
```text
分隔符="----"
user1@gmail.com----MyPassword123
user2@gmail.com----P@ssw0rd!%%99
```

**带 2FA 无辅助邮箱**:
```text
分隔符="----"
user1@gmail.com----MyPassword123----ABCD1234EFGH5678
user2@gmail.com----P@ssw0rd!%%99----WXYZ9012STUV3456
```

#### 注意事项

1. **密码特殊字符**: 支持所有特殊字符（`@#$%^&*` 等）
2. **空行**: 会被自动忽略
3. **注释**: 以 `#` 开头的行会被忽略
4. **字段顺序**: 必须按照 `邮箱-密码-辅助邮箱-2FA` 的顺序
5. **分隔符一致性**: 一个文件只能使用一种分隔符

#### 导入到数据库

**方式一：通过 Web 界面**

1. 访问 http://localhost:5173/accounts
2. 点击"导入账号"按钮
3. 选择 `accounts.txt` 文件
4. 点击"确认导入"

**方式二：自动导入**

程序启动时会自动检测 `accounts.txt` 并导入到数据库。

## 代理配置

### proxies.txt

代理 IP 配置文件，每行一个代理。

#### 格式

**Socks5 代理**:
```text
socks5://username:password@host:port
```

**HTTP 代理**:
```text
http://username:password@host:port
```

**无认证代理**:
```text
socks5://host:port
http://host:port
```

#### 示例

```text
socks5://user1:pass1@proxy1.example.com:1080
socks5://user2:pass2@proxy2.example.com:1080
http://user3:pass3@proxy3.example.com:8080
```

#### 代理分配

代理会按顺序分配给账号：

```
账号1 -> 代理1
账号2 -> 代理2
账号3 -> 代理3
账号4 -> 代理1  # 循环使用
```

#### 注意事项

1. **代理数量**: 建议代理数量 ≥ 账号数量
2. **代理质量**: 使用稳定的住宅代理或数据中心代理
3. **代理地区**: 建议使用与账号注册地相同的代理
4. **代理测试**: 使用前测试代理是否可用

## 虚拟卡配置

### cards.txt

虚拟卡信息配置文件，用于年龄验证和绑卡。

#### 格式

```
卡号 月份 年份 CVV
```

字段之间用**空格**分隔。

#### 字段说明

| 字段 | 说明 | 格式 | 示例 |
|------|------|------|------|
| 卡号 | 13-19位数字 | 纯数字 | `5481087170529907` |
| 月份 | 过期月份 | 01-12 | `01` |
| 年份 | 过期年份后两位 | YY | `32` (2032年) |
| CVV | 安全码 | 3-4位数字 | `536` |

#### 示例

```text
5481087170529907 01 32 536
5481087143137903 12 28 749
4532123456789012 06 30 123
```

#### 注意事项

1. **虚拟卡**: 建议使用虚拟卡，避免真实卡信息泄露
2. **卡片状态**: 确保卡片有效且有余额
3. **卡片地区**: 使用与账号地区匹配的卡片
4. **安全性**: 不要提交真实卡号到 Git 仓库

#### 推荐虚拟卡服务

- **HolyCard**: https://www.holy-card.com/
  - 支持 Gemini 订阅、GPT Team、0刀 Plus
  - 价格低至 2 元/张

## 数据库配置

### config 表

系统配置存储在数据库的 `config` 表中。

#### 配置项

| Key | 说明 | 示例值 |
|-----|------|--------|
| `sheerid_api_key` | SheerID API 密钥 | `cdk_xxx...` |
| `card_number` | 虚拟卡号 | `5481087170529907` |
| `card_exp_month` | 卡过期月份 | `01` |
| `card_exp_year` | 卡过期年份 | `32` |
| `card_cvv` | 卡 CVV | `536` |
| `card_zip` | 卡邮编 | `10001` |

#### 通过 Web 界面配置

1. 访问 http://localhost:5173/tasks
2. 点击"⚙️ 配置"按钮
3. 填写配置信息
4. 点击"保存"

#### 通过 API 配置

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

## 环境变量

### 支持的环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `CARD_NUMBER` | 虚拟卡号 | - |
| `CARD_CVV` | 卡 CVV | - |
| `CARD_EXP_MONTH` | 卡过期月份 | - |
| `CARD_EXP_YEAR` | 卡过期年份 | - |
| `CARD_ZIP` | 卡邮编 | - |
| `SHEERID_API_KEY` | SheerID API Key | - |

### 设置环境变量

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

### .env 文件

创建 `.env` 文件（已在 `.gitignore` 中）：

```bash
CARD_NUMBER=5481087170529907
CARD_CVV=536
CARD_EXP_MONTH=01
CARD_EXP_YEAR=32
CARD_ZIP=10001
SHEERID_API_KEY=your_api_key
```

## BitBrowser 配置

### API 地址

默认: `http://127.0.0.1:54345`

如果 BitBrowser 使用不同端口，需要修改代码中的 `BASE_URL`。

### 窗口配置

在 `create_window.py` 中配置默认窗口参数：

```python
DEFAULT_CONFIG = {
    "proxyMethod": 2,  # 2=自定义代理, 3=无代理
    "proxyType": "socks5",  # socks5 或 http
    "fingerprint": {
        "language": "en-US",
        "timezone": "America/New_York",
        "webrtc": "disabled"
    }
}
```

## 任务配置

### 并发数

控制同时运行的浏览器数量。

**推荐值**:
- 8GB 内存: 1-2
- 16GB 内存: 2-3
- 32GB 内存: 3-5

**配置方式**:
- Web 界面: 任务页面的"并发数"滑块
- API: `concurrency` 参数

### 任务超时

在 `web/backend/routers/tasks.py` 中配置：

```python
TASK_TIMEOUT = 300  # 5 分钟
```

### 关闭浏览器

任务完成后是否关闭浏览器窗口。

**配置方式**:
- Web 界面: "完成后关闭"复选框
- API: `close_after` 参数

## 日志配置

### 日志级别

在 `web/backend/main.py` 中配置：

```python
import logging

logging.basicConfig(
    level=logging.INFO,  # DEBUG, INFO, WARNING, ERROR
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### 日志文件

输出日志到文件：

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

## 数据库配置

### 数据库路径

默认: `accounts.db`（项目根目录）

修改路径：

```python
# database.py
DB_PATH = "/path/to/your/database.db"
```

### 数据库备份

定期备份数据库：

```bash
# 手动备份
cp accounts.db accounts.db.backup

# 自动备份（cron）
0 2 * * * cp /path/to/accounts.db /path/to/backups/accounts.db.$(date +\%Y\%m\%d)
```

## 前端配置

### API 地址

在 `web/frontend/src/api/index.js` 中配置：

```javascript
const API_BASE_URL = 'http://localhost:8000'
const WS_BASE_URL = 'ws://localhost:8000'
```

### 端口配置

在 `web/frontend/vite.config.js` 中配置：

```javascript
export default defineConfig({
  server: {
    port: 5173,  // 前端端口
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
```

## 安全配置

### 敏感文件保护

确保以下文件在 `.gitignore` 中：

```gitignore
accounts.txt
cards.txt
proxies.txt
*.db
.env
.env.local
```

### 数据加密

建议对敏感配置文件加密：

```bash
# 使用 GPG 加密
gpg -c accounts.txt

# 解密
gpg accounts.txt.gpg
```

### 访问控制

后端仅监听 `localhost`，不对外暴露：

```python
# web/backend/main.py
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
```

## 配置验证

### 检查配置

```bash
# 检查账号配置
python -c "from database import DBManager; print(DBManager.get_account_count())"

# 检查 BitBrowser 连接
curl http://127.0.0.1:54345/browser/list

# 检查后端 API
curl http://localhost:8000/accounts
```

### 配置测试

```python
# test_config.py
from database import DBManager
from web.backend.routers.config import get_config

# 测试数据库
print(f"账号数量: {DBManager.get_account_count()}")

# 测试配置
print(f"SheerID API Key: {get_config('sheerid_api_key')}")
print(f"卡号: {get_config('card_number')}")
```

## 配置最佳实践

1. **分离敏感信息**: 使用环境变量或数据库配置，不要硬编码
2. **定期备份**: 备份数据库和配置文件
3. **版本控制**: 不要提交敏感文件到 Git
4. **加密存储**: 对敏感配置文件加密
5. **权限控制**: 限制配置文件的访问权限
6. **配置验证**: 启动前验证配置是否正确
7. **文档更新**: 配置变更时更新文档

## 故障排查

### 配置文件读取失败

**原因**:
- 文件不存在
- 文件格式错误
- 编码问题

**解决**:
```bash
# 检查文件是否存在
ls -la accounts.txt

# 检查文件编码
file accounts.txt

# 转换编码
iconv -f GBK -t UTF-8 accounts.txt > accounts_utf8.txt
```

### 数据库配置不生效

**原因**:
- 配置未保存
- 缓存问题
- 数据库锁定

**解决**:
```python
# 清除缓存
from web.backend.routers.config import get_config
get_config.cache_clear()

# 重启服务
```

### 环境变量不生效

**原因**:
- 未激活虚拟环境
- 环境变量未导出
- 变量名错误

**解决**:
```bash
# 检查环境变量
echo $CARD_NUMBER

# 重新导出
export CARD_NUMBER="5481087170529907"

# 重启服务
```
