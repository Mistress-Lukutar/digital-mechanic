@echo off
setlocal EnableExtensions
REM ----------------------------------------------------------------
REM Deployment bootstrap: fetch the issued manual PDFs / case DOCX
REM from the shared storage link (MANUALS_DOWNLOAD_URL in the
REM gitignored .env) and build + cache the search index (BM25 +
REM embeddings) in the gitignored data/rag. Idempotent: re-runs are
REM cheap cache hits. The link and the documents never enter git.
REM Usage: scripts\bootstrap.bat [--no-embed] [--force-index]
REM ----------------------------------------------------------------
pushd "%~dp0.."
set "REPO=%CD%"
popd

if not exist "%REPO%\.venv\Scripts\python.exe" (
    echo ERROR: .venv not found in %REPO%
    echo Create it first:  python -m venv .venv
    echo then:             .venv\Scripts\pip install -e ".[dev]"
    echo and:              .venv\Scripts\pip install -r rag\requirements.txt
    exit /b 1
)

"%REPO%\.venv\Scripts\python.exe" "%REPO%\scripts\bootstrap.py" %*
