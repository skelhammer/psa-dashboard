#!/usr/bin/env bash
set -e

echo "============================================="
echo "  PSA Dashboard - Starting..."
echo "============================================="
echo

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Check for config
if [ ! -f config.yaml ]; then
    echo "[!] config.yaml not found. Copy config.example.yaml and fill in your settings."
    exit 1
fi

# Backend setup
echo "[1/4] Setting up backend..."
cd backend
if [ ! -d .venv ]; then
    echo "       Creating virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -r requirements.txt -q 2>/dev/null
cd ..

# Frontend setup
echo "[2/4] Setting up frontend..."
cd frontend
if [ ! -d node_modules ]; then
    echo "       Installing npm dependencies..."
    npm install
fi
cd ..

# Cleanup on exit
cleanup() {
    echo
    echo "Shutting down..."
    kill "$BACKEND_PID" 2>/dev/null
    kill "$FRONTEND_PID" 2>/dev/null
    wait 2>/dev/null
    echo "Stopped."
}
trap cleanup EXIT INT TERM

# Launch backend
echo "[3/4] Starting backend on :8880..."
cd backend
source .venv/bin/activate
python run.py &
BACKEND_PID=$!
cd ..

# Launch frontend
echo "[4/4] Starting frontend on :3000..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo
echo "============================================="
echo "  PSA Dashboard is running!"
echo "  Frontend: http://localhost:3000"
echo "  Backend:  http://localhost:8880"
echo "============================================="
echo
echo "Press Ctrl+C to stop."

wait
