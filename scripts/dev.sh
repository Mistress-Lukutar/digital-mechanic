#!/usr/bin/env bash
# Digital Mechanic - development startup: mock services + API (:8000,
# autoreload) + vite dev server (:5173, proxies /api -> 8000).
set -euo pipefail

API_PORT="${API_PORT:-8000}"
ML_PORT="${ML_PORT:-8001}"
TOIR_PORT="${TOIR_PORT:-8002}"
RAG_PORT="${RAG_PORT:-8003}"

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
# Keep the backend's RAG client in sync with the port below (its default
# is http://127.0.0.1:8003, but env wins over .env).
export RAG_API_URL="http://127.0.0.1:$RAG_PORT"

"$PY" -m uvicorn mock_ml.app:app --port "$ML_PORT" --app-dir "$REPO/vendor" &
ML_PID=$!
"$PY" -m uvicorn mock_toir.app:app --port "$TOIR_PORT" --app-dir "$REPO/vendor" &
TOIR_PID=$!

# RAG manual-search service (rag/, participant B) - optional: when it is
# down the backend falls back to mock chunks. rag's relative default
# paths (data/rag, data/manuals) resolve against the process CWD, so it
# must run from the repo root.
RAG_PID=""
if [[ ! -f "$REPO/data/rag/current.json" ]]; then
  echo "[dev] RAG skipped: no index - build it first: $PY -m rag.setup --from <pdfs dir>"
elif ! (cd "$REPO" && "$PY" -c "import rag.service" >/dev/null 2>&1); then
  echo "[dev] RAG skipped: deps missing - install: pip install -r rag/requirements.txt"
else
  (cd "$REPO" && "$PY" -m uvicorn rag.service:app --port "$RAG_PORT" --app-dir "$REPO") &
  RAG_PID=$!
fi
(cd "$REPO/frontend" && npm run dev) &
UI_PID=$!
trap 'kill "$ML_PID" "$TOIR_PID" ${RAG_PID:+"$RAG_PID"} "$UI_PID" 2>/dev/null || true' EXIT

echo "[dev] UI (vite):  http://localhost:5173/  (open localhost - vite listens on IPv6)"
echo "[dev] API:        http://127.0.0.1:$API_PORT/  (health: /health)"
echo "[dev] mocks: ML :$ML_PORT, TOiR :$TOIR_PORT, RAG :$RAG_PORT - Ctrl+C stops everything"
cd "$REPO"
"$PY" -m uvicorn mechanic.main:app --port "$API_PORT" --reload
