#!/bin/bash
# 启动 Web UI 前端

cd "$(dirname "$0")/frontend"

echo "启动 Auto BitBrowser Web 前端..."
echo "访问地址: http://localhost:5173"
echo ""

npm run dev
