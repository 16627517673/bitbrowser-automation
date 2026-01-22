#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_CMD=(uv run python -m uvicorn web.backend.main:app --reload --host 0.0.0.0 --port 8000)
FRONTEND_DIR="$ROOT_DIR/web/frontend"

echo "Starting Auto BitBrowser Web UI..."
echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo ""

if ! command -v uv >/dev/null 2>&1; then
  echo "[error] uv not found, please install uv first."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[error] npm not found, please install Node.js first."
  exit 1
fi

if [ ! -d "$ROOT_DIR/.venv" ]; then
  echo "[info] Creating Python env with uv..."
  (cd "$ROOT_DIR" && uv sync)
fi

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "[info] Installing frontend dependencies..."
  (cd "$FRONTEND_DIR" && npm install)
fi

(cd "$ROOT_DIR" && "${BACKEND_CMD[@]}") &
BACKEND_PID=$!

cleanup() {
  echo ""
  echo "Stopping Web UI..."
  kill "$BACKEND_PID" >/dev/null 2>&1 || true
  if [ -n "${FRONTEND_PID:-}" ]; then
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

(cd "$FRONTEND_DIR" && npm run dev) &
FRONTEND_PID=$!

wait "$BACKEND_PID" "$FRONTEND_PID"
