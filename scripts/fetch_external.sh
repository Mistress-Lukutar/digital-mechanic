#!/usr/bin/env bash
# Download and unpack the password-protected bundle of RAG eval sets
# and the manual prompt block. The link and the password come from
# EXTERNAL_CONTENT_URL / EXTERNAL_CONTENT_PASSWORD, which live in the
# gitignored .env (never commit them).
# Needs: pip install pyzipper
# Usage: scripts/fetch_external.sh [--list] [--from FILE] [--allow-plain]
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -x "$REPO/.venv/Scripts/python.exe" ]]; then
  PY="$REPO/.venv/Scripts/python.exe"   # Windows venv layout
elif [[ -x "$REPO/.venv/bin/python" ]]; then
  PY="$REPO/.venv/bin/python"           # POSIX venv layout
else
  PY=python3
fi

exec "$PY" "$REPO/scripts/fetch_external.py" "$@"
