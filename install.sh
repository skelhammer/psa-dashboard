#!/usr/bin/env bash
# PSA Dashboard - Ubuntu Install Script
# Installs the app under /opt/psa-dashboard and creates systemd services.
# Run as root or with sudo.
set -euo pipefail

APP_DIR="/opt/psa-dashboard"
APP_USER="psa-dashboard"
NODE_MAJOR=22

# ---------- pre-flight ----------
if [[ $EUID -ne 0 ]]; then
    echo "Error: run this script as root (sudo bash install.sh)"
    exit 1
fi

echo "============================================="
echo "  PSA Dashboard - Ubuntu Installer"
echo "============================================="
echo

# ---------- system packages ----------
echo "[1/7] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip curl ca-certificates gnupg nginx >/dev/null

# Node.js via NodeSource (if not already installed)
if ! command -v node &>/dev/null || [[ "$(node -v | cut -d. -f1 | tr -d v)" -lt "$NODE_MAJOR" ]]; then
    echo "       Installing Node.js ${NODE_MAJOR}.x..."
    mkdir -p /etc/apt/keyrings
    curl -fsSL "https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key" \
        | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg --yes
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list
    apt-get update -qq
    apt-get install -y -qq nodejs >/dev/null
fi

echo "       Python: $(python3 --version)"
echo "       Node:   $(node --version)"

# ---------- app user ----------
echo "[2/7] Creating service account..."
if ! id "$APP_USER" &>/dev/null; then
    useradd --system --shell /usr/sbin/nologin --home-dir "$APP_DIR" "$APP_USER"
fi

# ---------- copy files ----------
echo "[3/7] Copying application to ${APP_DIR}..."
mkdir -p "$APP_DIR"
# Copy everything except .git, node_modules, .venv, __pycache__
rsync -a --delete \
    --exclude='.git' \
    --exclude='node_modules' \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='config.yaml' \
    "$(dirname "$(readlink -f "$0")")/" "$APP_DIR/"

# Ensure config.yaml exists
if [[ ! -f "$APP_DIR/config.yaml" ]]; then
    cp "$APP_DIR/config.example.yaml" "$APP_DIR/config.yaml"
    echo "       Created config.yaml from example. Edit it with your settings:"
    echo "       sudo nano ${APP_DIR}/config.yaml"
fi

# Ensure data directory exists for SQLite
mkdir -p "$APP_DIR/backend/data"

chown -R "$APP_USER":"$APP_USER" "$APP_DIR"

# ---------- backend venv ----------
echo "[4/7] Setting up Python virtual environment..."
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/backend/.venv"
sudo -u "$APP_USER" "$APP_DIR/backend/.venv/bin/pip" install --upgrade pip -q 2>/dev/null
sudo -u "$APP_USER" "$APP_DIR/backend/.venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt" -q 2>/dev/null

# ---------- frontend build ----------
echo "[5/7] Building frontend for production..."
cd "$APP_DIR/frontend"
sudo -u "$APP_USER" npm install --no-fund --no-audit 2>/dev/null
sudo -u "$APP_USER" npm run build 2>/dev/null
echo "       Frontend built to ${APP_DIR}/frontend/dist"

# ---------- systemd service ----------
echo "[6/7] Creating systemd service..."
cat > /etc/systemd/system/psa-dashboard.service <<EOF
[Unit]
Description=PSA Dashboard Backend
After=network.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}/backend
ExecStart=${APP_DIR}/backend/.venv/bin/python -m uvicorn app.api.main:create_app --factory --host 127.0.0.1 --port 8880
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable psa-dashboard.service

# ---------- nginx ----------
echo "[7/7] Configuring nginx..."
cat > /etc/nginx/sites-available/psa-dashboard <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    # Serve the built frontend
    root ${APP_DIR}/frontend/dist;
    index index.html;

    # API requests proxy to the backend
    location /api/ {
        proxy_pass http://127.0.0.1:8880;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # SPA fallback: serve index.html for client-side routes
    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
EOF

# Enable site, disable default if it conflicts
ln -sf /etc/nginx/sites-available/psa-dashboard /etc/nginx/sites-enabled/psa-dashboard
rm -f /etc/nginx/sites-enabled/default
nginx -t 2>/dev/null
systemctl enable nginx
systemctl restart nginx

# ---------- start ----------
systemctl start psa-dashboard.service

echo
echo "============================================="
echo "  Installation complete!"
echo "============================================="
echo
echo "  Dashboard:  http://<your-server-ip>"
echo "  Backend:    http://127.0.0.1:8880 (proxied via nginx)"
echo
echo "  Config:     ${APP_DIR}/config.yaml"
echo "  Logs:       journalctl -u psa-dashboard -f"
echo
echo "  Commands:"
echo "    sudo systemctl restart psa-dashboard   # restart backend"
echo "    sudo systemctl stop psa-dashboard      # stop backend"
echo "    sudo systemctl status psa-dashboard    # check status"
echo
echo "  Edit your config.yaml, then restart the service to apply changes."
echo "============================================="
