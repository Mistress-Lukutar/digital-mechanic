@echo off
setlocal EnableExtensions
echo ================================================================
echo                Digital Mechanic - Startup Script
echo ================================================================
echo.

:: ----------------------------------------------------------------
:: CONFIGURATION
:: ----------------------------------------------------------------
:: Public port of the API/UI process (the reverse proxy on the VPS
:: forwards a site subpath to this port through the tunnel).
set PORT=8011
set HOST=0.0.0.0

:: Mock integration services (ML diagnostics and maintenance system).
set ML_PORT=8001
set TOIR_PORT=8002

:: RAG manual-search service (rag\, participant B).
set RAG_PORT=8003

:: ----------------------------------------------------------------
:: Resolve repo root (this script lives in scripts\)
:: ----------------------------------------------------------------
pushd "%~dp0.."
set "REPO=%CD%"
popd

if not exist "%REPO%\.venv\Scripts\python.exe" (
    echo ERROR: .venv not found in %REPO%
    echo Create it first:  python -m venv .venv
    echo then:             .venv\Scripts\pip install -e ".[dev]"
    pause
    exit /b 1
)

:: ----------------------------------------------------------------
:: [1/2] Frontend build - served statically by the API process.
:: The vite build uses a relative base, so one static/dist works
:: both at the server root and behind a subpath reverse proxy.
:: ----------------------------------------------------------------
if exist "%REPO%\static\dist\index.html" (
    echo [1/2] Frontend build found: static\dist
) else (
    echo [1/2] static\dist not found - building frontend...
    pushd "%REPO%\frontend"
    call npm run build
    if errorlevel 1 (
        popd
        echo ERROR: frontend build failed
        pause
        exit /b 1
    )
    popd
)
echo.

:: ----------------------------------------------------------------
:: [2/2] Start mock services in separate windows, then the API.
:: The stubs need MOCK_DATA_PATH pointing at the issued fleet file.
:: ----------------------------------------------------------------
echo [2/2] Starting services...
set "MOCK_DATA_PATH=%REPO%\data\vehicles.json"
start "DM mock ML :%ML_PORT%" /min cmd /k ""%REPO%\.venv\Scripts\python.exe" -m uvicorn mock_ml.app:app --port %ML_PORT% --app-dir "%REPO%\vendor""
start "DM mock TOiR :%TOIR_PORT%" /min cmd /k ""%REPO%\.venv\Scripts\python.exe" -m uvicorn mock_toir.app:app --port %TOIR_PORT% --app-dir "%REPO%\vendor""

:: RAG manual-search service - optional: when it is down the backend
:: falls back to mock chunks. rag's relative default paths (data\rag,
:: data\manuals) resolve against the process CWD, so the window is
:: started with /D "%REPO%".
set "RAG_API_URL=http://127.0.0.1:%RAG_PORT%"
if not exist "%REPO%\data\rag\current.json" goto rag_no_index
pushd "%REPO%"
".venv\Scripts\python.exe" -c "import rag.service" >nul 2>&1
if errorlevel 1 (
    popd
    goto rag_no_deps
)
popd
start "DM RAG :%RAG_PORT%" /min /D "%REPO%" cmd /k ""%REPO%\.venv\Scripts\python.exe" -m uvicorn rag.service:app --port %RAG_PORT% --app-dir "%REPO%""
goto rag_done
:rag_no_index
echo [start] RAG skipped: no index - build it first: python -m rag.setup --from "C:\path\to\pdfs"
goto rag_done
:rag_no_deps
echo [start] RAG skipped: deps missing - install: .venv\Scripts\pip install -r rag\requirements.txt
:rag_done

echo.
echo ----------------------------------------------------------------
echo   API + UI:  http://localhost:%PORT%/
echo   Health:    http://localhost:%PORT%/health
echo   Mocks:     ML :%ML_PORT%, TOiR :%TOIR_PORT%, RAG :%RAG_PORT% (separate windows)
echo   Press Ctrl+C to stop the API server
echo ----------------------------------------------------------------
echo.
cd /d "%REPO%"
.venv\Scripts\python.exe -m uvicorn mechanic.main:app --host %HOST% --port %PORT%

echo.
echo API server stopped.
pause
