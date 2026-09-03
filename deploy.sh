#!/bin/bash
# Deploy BG Real Estate Intel (PocketBroker).
#   Frontend: Vue 3 + Vite  → built static → /var/www/pocketbroker/
#   Backend:  FastAPI/uvicorn (systemd unit pocketbroker-api, 127.0.0.1:8000)
# Run from anywhere — it resolves its own path. Reads secrets from
# /home/deploy/secrets/pocketbroker.env (kept OUTSIDE the repo). Service restart uses sudo.
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Pulling latest code..."
git -C "$PROJECT_DIR" pull origin main

echo "==> Building frontend..."
cd "$PROJECT_DIR/frontend"
npm ci
# Build-time config (e.g. VITE_GA_ID for Google Analytics) lives in the
# out-of-repo secrets file, like the backend's. Vite picks up any VITE_* var
# already present in the environment. Harmless if the file is absent.
if [ -f /home/deploy/secrets/pocketbroker.env ]; then
  set -a; source /home/deploy/secrets/pocketbroker.env; set +a
fi
npm run build

echo "==> Deploying frontend to /var/www/pocketbroker/..."
rsync -a --delete "$PROJECT_DIR/frontend/dist/" /var/www/pocketbroker/

echo "==> Installing backend deps..."
cd "$PROJECT_DIR/backend"
.venv/bin/pip install -q -r requirements.txt

echo "==> Running DB migrations (alembic upgrade head)..."
set -a; source /home/deploy/secrets/pocketbroker.env; set +a
.venv/bin/alembic upgrade head

echo "==> Generating sitemap.xml..."
PYTHONPATH=. .venv/bin/python scripts/generate_sitemap.py /var/www/pocketbroker/sitemap.xml

echo "==> Restarting backend service..."
sudo systemctl restart pocketbroker-api

echo "==> Done. App live at https://app.example.com"
