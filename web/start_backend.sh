#!/bin/bash
# 启动 Web UI 后端

cd "$(dirname "$0")/.."

echo "启动 Auto BitBrowser Web API..."
echo "API 地址: http://localhost:8000"
echo "API 文档: http://localhost:8000/docs"
echo ""

# 激活虚拟环境（如果存在）
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# 启动 FastAPI
python -m uvicorn web.backend.main:app --reload --host 0.0.0.0 --port 8000
