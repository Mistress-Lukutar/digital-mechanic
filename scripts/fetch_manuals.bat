@echo off
setlocal EnableExtensions
REM ----------------------------------------------------------------
REM Download the issued manual PDFs / case DOCX from the shared
REM storage link. The link comes from MANUALS_DOWNLOAD_URL, which
REM lives in the gitignored .env (never commit the link itself).
REM Usage: scripts\fetch_manuals.bat [--list] [--ext pdf] [--to DIR]
REM ----------------------------------------------------------------
pushd "%~dp0.."
set "REPO=%CD%"
popd

if not exist "%REPO%\.venv\Scripts\python.exe" (
    echo ERROR: .venv not found in %REPO%
    echo Create it first:  python -m venv .venv
    exit /b 1
)

"%REPO%\.venv\Scripts\python.exe" "%REPO%\scripts\fetch_manuals.py" %*
