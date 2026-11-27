@echo off
setlocal EnableExtensions
REM ----------------------------------------------------------------
REM Download and unpack the password-protected bundle of RAG eval
REM sets and the manual prompt block. The link and the password come
REM from EXTERNAL_CONTENT_URL / EXTERNAL_CONTENT_PASSWORD, which live
REM in the gitignored .env (never commit them).
REM Needs: pip install pyzipper
REM Usage: scripts\fetch_external.bat [--list] [--from FILE] [--allow-plain]
REM ----------------------------------------------------------------
pushd "%~dp0.."
set "REPO=%CD%"
popd

if not exist "%REPO%\.venv\Scripts\python.exe" (
    echo ERROR: .venv not found in %REPO%
    echo Create it first:  python -m venv .venv
    exit /b 1
)

"%REPO%\.venv\Scripts\python.exe" "%REPO%\scripts\fetch_external.py" %*
