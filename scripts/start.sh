#!/usr/bin/env bash
# Digital Mechanic - one-command startup: mock services + API/UI server.
# The API process serves the built frontend (static/dist) and listens on
# $HOST:$PORT; the reverse proxy forwards a site subpath to this port.
set -euo pipefail

PORT="${PORT:-8011}"
HOST="${HOST:-0.0.0.0}"
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

# Build the frontend when the bundle is missing OR older than the sources
# (stale-bundle guard: a git pull without npm build must not serve the old
# UI). The vite build uses a relative base, so a single static/dist works
# both at the server root and behind a subpath proxy.
if [[ ! -f "$REPO/static/dist/index.html" ]] \
   || [[ -n "$(find "$REPO/frontend/src" -newer "$REPO/static/dist/index.html" -print -quit 2>/dev/null)" ]]; then
  echo "[start] building frontend (missing or older than sources)..."
  (cd "$REPO/frontend" && npm run build)
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
  echo "[start] RAG skipped: no index - build it first: $PY -m rag.setup --from <pdfs dir>"
elif ! (cd "$REPO" && "$PY" -c "import rag.service" >/dev/null 2>&1); then
  echo "[start] RAG skipped: deps missing - install: pip install -r rag/requirements.txt"
else
  (cd "$REPO" && "$PY" -m uvicorn rag.service:app --port "$RAG_PORT" --app-dir "$REPO") &
  RAG_PID=$!
fi
trap 'kill "$ML_PID" "$TOIR_PID" ${RAG_PID:+"$RAG_PID"} 2>/dev/null || true' EXIT

echo "[start] API + UI: http://localhost:$PORT/  (health: /health)"
echo "[start] mocks: ML :$ML_PORT, TOiR :$TOIR_PORT, RAG :$RAG_PORT - Ctrl+C stops everything"
# Stale-backend guard: an old API process on $PORT makes uvicorn exit with
# "address already in use" - warn explicitly (observed once on the stand).
if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -q ":$PORT "; then
  echo "[start] WARNING: port $PORT is already in use - stop the old API process first."
fi
cd "$REPO"
"$PY" -m uvicorn mechanic.main:app --host "$HOST" --port "$PORT"
