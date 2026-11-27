#!/usr/bin/env bash
# Deployment bootstrap: fetch the issued manual PDFs / case DOCX from
# the shared storage link (MANUALS_DOWNLOAD_URL in the gitignored .env)
# and build + cache the search index (BM25 + embeddings) in the
# gitignored data/rag. Idempotent: re-runs are cheap cache hits. The
# link and the documents never enter git.
# Usage: scripts/bootstrap.sh [--no-embed] [--force-index]
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -x "$REPO/.venv/Scripts/python.exe" ]]; then
  PY="$REPO/.venv/Scripts/python.exe"   # Windows venv layout
elif [[ -x "$REPO/.venv/bin/python" ]]; then
  PY="$REPO/.venv/bin/python"           # POSIX venv layout
else
  PY=python3
fi

exec "$PY" "$REPO/scripts/bootstrap.py" "$@"
