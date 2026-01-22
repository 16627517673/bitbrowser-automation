# Quick Start

## Requirements

### Required Software

- **Python**: 3.11 or higher (3.12 recommended)
- **Node.js**: 18 or higher
- **uv**: Python package manager
- **BitBrowser**: Fingerprint browser client

### System Requirements

- **Operating System**: Windows 10+, macOS 10.15+, Linux
- **Memory**: Minimum 8GB (16GB recommended)
- **Disk Space**: At least 5GB available

## Installation

### 1. Clone the Project

```bash
git clone https://github.com/yourusername/auto_bitbrowser.git
cd auto_bitbrowser
```

### 2. Install Python Dependencies

Use `uv` to manage Python environment:

```bash
# Install uv (if not already installed)
pip install uv

# Create virtual environment and install dependencies
uv sync
```

This will create a `.venv` directory and install all Python dependencies.

### 3. Install Playwright Browsers

```bash
# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate  # Windows

# Install Playwright browsers
playwright install chromium
```

### 4. Install Frontend Dependencies

```bash
cd web/frontend
npm install
cd ../..
```

### 5. Prepare Configuration Files

Create account configuration files:

```bash
# Copy example files
cp accounts_example.txt accounts.txt
cp cards_example.txt cards.txt

# Edit configuration files
nano accounts.txt  # or use your preferred editor
```

## Starting Services

### Method 1: One-Click Start (Recommended)

```bash
./start_web.sh
```

This will start both backend and frontend services.

### Method 2: Manual Start

**Start Backend**:
```bash
cd web/backend
uvicorn main:app --reload --port 8000
```

**Start Frontend** (new terminal):
```bash
cd web/frontend
npm run dev
```

## Access the Application

After successful startup, access in your browser:

- **Frontend Interface**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

## First-Time Usage

### 1. Import Accounts

**Method 1: Import from File**

Edit the `accounts.txt` file:

```text
分隔符="----"
user1@gmail.com----password123----backup1@email.com----ABCD1234EFGH5678
user2@gmail.com----password456----backup2@email.com----WXYZ9012STUV3456
```

Then click the "Import Accounts" button in the frontend.

**Method 2: Add via Web Interface**

1. Visit http://localhost:5173/accounts
2. Click the "Add Account" button
3. Fill in account information
4. Click "Save"

### 2. Configure SheerID API Key (Optional)

If you need to use SheerID verification:

1. Visit http://localhost:5173/tasks
2. Click the "⚙️ Config" button
3. Fill in SheerID API Key
4. Click "Save"

### 3. Configure Virtual Card Information (Optional)

If you need to use age verification or card binding:

1. Fill in card number, expiration date, CVV, and ZIP code in the config panel
2. Click "Save"

### 4. Create Browser Windows

1. Visit http://localhost:5173/browsers
2. Click the "Restore Windows" button
3. The system will create browser windows for all accounts

### 5. Execute Tasks

1. Visit http://localhost:5173/tasks
2. Select accounts to process
3. Select task types (Setup 2FA, Age Verification, etc.)
4. Set concurrency level
5. Click "Start Execution"

## Common Issues

### Q: "ModuleNotFoundError" when starting backend

**A**: Make sure the virtual environment is activated:

```bash
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate  # Windows
```

### Q: Frontend cannot connect to backend

**A**: Check if the backend is running properly:

```bash
curl http://localhost:8000/accounts
```

If no response, check backend logs.

### Q: BitBrowser API connection failed

**A**: Make sure BitBrowser client is running and API port is 54345:

```bash
curl http://127.0.0.1:54345/browser/list
```

### Q: Playwright browser connection failed

**A**: Check if browser window is open:

1. View window list in BitBrowser client
2. Ensure window status is "Running"
3. Check if WebSocket endpoint is correct

### Q: Task execution failed

**A**: Check real-time logs, common causes:

- Incorrect account password
- Incorrect proxy configuration
- Network connection issues
- Missing configuration information

## Next Steps

- Read [Configuration Guide](./configuration.md) for detailed configuration
- Read [Architecture Design](./architecture.md) to understand system architecture
- Read [Task System](./task-system.md) to understand task execution flow
- Read [Browser Management](./browser-management.md) to understand window management

## Getting Help

If you encounter problems:

1. Check [Debugging Tips](./debugging.md)
2. Check GitHub Issues
3. Check backend logs and frontend console

## Stopping Services

### Stop One-Click Started Services

Press `Ctrl+C` to stop the `start_web.sh` script.

### Stop Manually Started Services

Press `Ctrl+C` in each terminal.

## Uninstallation

```bash
# Remove virtual environment
rm -rf .venv

# Remove frontend dependencies
rm -rf web/frontend/node_modules

# Remove database (optional)
rm accounts.db

# Remove configuration files (optional)
rm accounts.txt cards.txt
```

## Updating

```bash
# Pull latest code
git pull

# Update Python dependencies
uv sync

# Update frontend dependencies
cd web/frontend
npm install
cd ../..

# Restart services
./start_web.sh
```
