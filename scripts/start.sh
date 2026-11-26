#!/usr/bin/env bash
# Digital Mechanic - one-command startup: mock services + API/UI server.
# The API process serves the built frontend (static/dist) and listens on
# $HOST:$PORT; the reverse proxy forwards a site subpath to this port.
set -euo pipefail

PORT="${PORT:-8011}"
HOST="${HOST:-0.0.0.0}"
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

# Build the frontend once; the vite build uses a relative base, so a single
# static/dist works both at the server root and behind a subpath proxy.
if [[ ! -f "$REPO/static/dist/index.html" ]]; then
  echo "[start] static/dist missing - building frontend..."
  (cd "$REPO/frontend" && npm run build)
fi

export MOCK_DATA_PATH="$REPO/data/vehicles.json"

"$PY" -m uvicorn mock_ml.app:app --port "$ML_PORT" --app-dir vendor &
ML_PID=$!
"$PY" -m uvicorn mock_toir.app:app --port "$TOIR_PORT" --app-dir vendor &
TOIR_PID=$!
trap 'kill "$ML_PID" "$TOIR_PID" 2>/dev/null || true' EXIT

echo "[start] API + UI: http://localhost:$PORT/  (health: /health)"
echo "[start] mocks: ML :$ML_PORT, TOiR :$TOIR_PORT - Ctrl+C stops everything"
cd "$REPO"
"$PY" -m uvicorn mechanic.main:app --host "$HOST" --port "$PORT"
