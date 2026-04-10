@echo off
title PSA Dashboard

echo =============================================
echo   PSA Dashboard - Starting...
echo =============================================
echo.

:: Check for config
if not exist config.yaml (
    echo [!] config.yaml not found. Copy config.example.yaml and fill in your settings.
    pause
    exit /b 1
)

:: Backend setup
echo [1/4] Setting up backend...
cd backend
if not exist .venv (
    echo       Creating virtual environment...
    python -m venv .venv
)
call .venv\Scripts\activate
pip install -r requirements.txt -q 2>nul
cd ..

:: Frontend setup
echo [2/4] Setting up frontend...
cd frontend
if not exist node_modules (
    echo       Installing npm dependencies...
    call npm install
)
cd ..

:: Launch backend
echo [3/4] Starting backend on :8880...
cd backend
start "PSA Dashboard - Backend" cmd /k ".venv\Scripts\activate && python run.py"
cd ..

:: Launch frontend
echo [4/4] Starting frontend on :3000...
cd frontend
start "PSA Dashboard - Frontend" cmd /k "npm run dev"
cd ..

echo.
echo =============================================
echo   PSA Dashboard is running!
echo   Frontend: http://localhost:3000
echo   Backend:  http://localhost:8880
echo =============================================
echo.
echo Close the Backend and Frontend windows to stop.
