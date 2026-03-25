#!/usr/bin/env bash
# PSA Dashboard - Update Script
# Pulls latest code, rebuilds frontend if changed, installs new deps if changed, and restarts.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$SCRIPT_DIR"

if [[ $EUID -ne 0 ]]; then
    echo "Error: run this script as root (sudo bash update.sh)"
    exit 1
fi

APP_USER="$(stat -c '%U' "$SCRIPT_DIR")"

echo "Pulling latest code..."
sudo -u "$APP_USER" git pull

# Check if Python deps changed
if git diff HEAD~1 --name-only | grep -q "backend/requirements.txt"; then
    echo "Python dependencies changed, installing..."
    sudo -u "$APP_USER" "$SCRIPT_DIR/backend/.venv/bin/pip" install -r "$SCRIPT_DIR/backend/requirements.txt" -q 2>/dev/null
fi

# Check if frontend changed
if git diff HEAD~1 --name-only | grep -q "^frontend/"; then
    echo "Frontend changed, rebuilding..."
    cd "$SCRIPT_DIR/frontend"
    sudo -u "$APP_USER" npm install --no-fund --no-audit 2>/dev/null
    sudo -u "$APP_USER" npm run build 2>/dev/null
    echo "Frontend rebuilt."
    cd "$SCRIPT_DIR"
else
    echo "No frontend changes, skipping rebuild."
fi

echo "Restarting service..."
systemctl restart psa-dashboard

echo "Done. Dashboard is updated and running."
