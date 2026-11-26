#!/usr/bin/env bash
# Digital Mechanic - development startup: mock services + API (:8000,
# autoreload) + vite dev server (:5173, proxies /api -> 8000).
set -euo pipefail

API_PORT="${API_PORT:-8000}"
ML_PORT="${ML_PORT:-8001}"
TOIR_PORT="${TOIR_PORT:-8002}"

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -x "$REPO/.venv/Scripts/python.exe" ]]; then
  PY="$REPO/.venv/Scripts/python.exe"   # Windows venv layout
elif [[ -x "$REPO/.venv/bin/python" ]]; then
  PY="$REPO/.venv/bin/python"           # POSIX venv layout
else
  echo "ERROR: .venv not found in $REPO" >&2
  echo "Create it first: python -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
  exit 1
fi

# Frontend dependencies for the vite dev server.
if [[ ! -d "$REPO/frontend/node_modules" ]]; then
  echo "[dev] installing frontend dependencies..."
  (cd "$REPO/frontend" && npm install)
fi

export MOCK_DATA_PATH="$REPO/data/vehicles.json"

"$PY" -m uvicorn mock_ml.app:app --port "$ML_PORT" --app-dir vendor &
ML_PID=$!
"$PY" -m uvicorn mock_toir.app:app --port "$TOIR_PORT" --app-dir vendor &
TOIR_PID=$!
(cd "$REPO/frontend" && npm run dev) &
UI_PID=$!
trap 'kill "$ML_PID" "$TOIR_PID" "$UI_PID" 2>/dev/null || true' EXIT

echo "[dev] UI (vite):  http://localhost:5173/  (open localhost - vite listens on IPv6)"
echo "[dev] API:        http://127.0.0.1:$API_PORT/  (health: /health)"
echo "[dev] mocks: ML :$ML_PORT, TOiR :$TOIR_PORT - Ctrl+C stops everything"
cd "$REPO"
"$PY" -m uvicorn mechanic.main:app --port "$API_PORT" --reload
