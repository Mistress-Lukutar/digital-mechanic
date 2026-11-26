@echo off
setlocal EnableExtensions
echo ================================================================
echo            Digital Mechanic - Development Startup
echo ================================================================
echo.

:: ----------------------------------------------------------------
:: CONFIGURATION
:: ----------------------------------------------------------------
:: The API port must stay 8000: the vite dev server proxies /api here.
set API_PORT=8000
set ML_PORT=8001
set TOIR_PORT=8002
set UI_PORT=5173

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

:: Frontend dependencies for the vite dev server.
if not exist "%REPO%\frontend\node_modules\" (
    echo Installing frontend dependencies...
    pushd "%REPO%\frontend"
    call npm install
    if errorlevel 1 (
        popd
        echo ERROR: npm install failed
        pause
        exit /b 1
    )
    popd
)
echo.

:: ----------------------------------------------------------------
:: Start mock services and the vite dev server in separate windows,
:: then the API with autoreload in this window. The stubs need
:: MOCK_DATA_PATH pointing at the issued fleet file.
:: ----------------------------------------------------------------
set "MOCK_DATA_PATH=%REPO%\data\vehicles.json"
start "DM mock ML :%ML_PORT%" /min cmd /k ""%REPO%\.venv\Scripts\python.exe" -m uvicorn mock_ml.app:app --port %ML_PORT% --app-dir vendor"
start "DM mock TOiR :%TOIR_PORT%" /min cmd /k ""%REPO%\.venv\Scripts\python.exe" -m uvicorn mock_toir.app:app --port %TOIR_PORT% --app-dir vendor"
start "DM frontend :%UI_PORT%" /D "%REPO%\frontend" cmd /k npm run dev

echo.
echo ----------------------------------------------------------------
echo   UI (vite dev):  http://localhost:%UI_PORT%/  (open localhost, vite is on IPv6)
echo   API:            http://127.0.0.1:%API_PORT%/  (health: /health)
echo   Mocks:          ML :%ML_PORT%, TOiR :%TOIR_PORT% (separate windows)
echo   Press Ctrl+C to stop the API server
echo ----------------------------------------------------------------
echo.
cd /d "%REPO%"
.venv\Scripts\python.exe -m uvicorn mechanic.main:app --port %API_PORT% --reload

echo.
echo API server stopped (mock and vite windows stay open - close them manually).
pause
