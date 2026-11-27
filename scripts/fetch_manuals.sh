#!/usr/bin/env bash
# Download the issued manual PDFs / case DOCX from the shared storage
# link. The link comes from MANUALS_DOWNLOAD_URL, which lives in the
# gitignored .env (never commit the link itself).
# Usage: scripts/fetch_manuals.sh [--list] [--ext pdf] [--to DIR]
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -x "$REPO/.venv/Scripts/python.exe" ]]; then
  PY="$REPO/.venv/Scripts/python.exe"   # Windows venv layout
elif [[ -x "$REPO/.venv/bin/python" ]]; then
  PY="$REPO/.venv/bin/python"           # POSIX venv layout
else
  PY=python3
fi

exec "$PY" "$REPO/scripts/fetch_manuals.py" "$@"
