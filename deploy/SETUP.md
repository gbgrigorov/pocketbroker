# PocketBroker — server setup runbook

One-time bring-up on the production VPS.

App layout:
- Frontend (Vue SPA) → `/var/www/pocketbroker/`  (served by nginx at the subdomain root)
- Backend (FastAPI/uvicorn) → systemd `pocketbroker-api`, bound to `127.0.0.1:8000`, proxied at `/api/`
- DB → local PostgreSQL, database `bg_realestate`
- Secrets → `/home/deploy/secrets/pocketbroker.env` (chmod 600, **outside the repo**)

**Progress (2026-06-07):**
- [x] Step 1 — PostgreSQL 16 installed, role + DB `bg_realestate` created
- [x] Step 2 — secrets written to `/home/deploy/secrets/pocketbroker.env`
- [x] Step 3 — DB dump restored + verified (schema at alembic head, backend serves data)
- [ ] Step 4 — install + enable systemd unit `pocketbroker-api` (sudo)
- [ ] Step 5 — `sudo cp` nginx source → live + reload (sudo)
- [ ] Step 6 — certbot HTTPS (sudo)

---

## 1. Install PostgreSQL + create the DB  (sudo)

```bash
sudo apt update && sudo apt install -y postgresql

# Create the role + database (pick a real password):
sudo -u postgres psql <<'SQL'
CREATE ROLE bg_realestate LOGIN PASSWORD 'YOUR_DB_PASSWORD';
CREATE DATABASE bg_realestate OWNER bg_realestate;
SQL
```

## 2. Fill in secrets  (your data)

Secrets live in `/home/deploy/secrets/pocketbroker.env` (chmod 600, outside the repo).
Set `DATABASE_URL` (with the step-1 password) and `SECRET_KEY`:

```
DATABASE_URL=postgresql+psycopg://bg_realestate:YOUR_DB_PASSWORD@localhost:5432/bg_realestate
```

## 3. Load the data  (your data)

Either **(a)** restore the dump you're uploading:

```bash
# plain SQL dump:
psql 'postgresql://bg_realestate:YOUR_DB_PASSWORD@localhost/bg_realestate' < your_dump.sql
# or custom-format dump:
pg_restore -d 'postgresql://bg_realestate:YOUR_DB_PASSWORD@localhost/bg_realestate' --no-owner your_dump.dump
```

…**or (b)** build the schema from migrations and run the ETL from the repo's
public data (the private ownership/builder/signal datasets are gitignored, so
they must be uploaded under `data/raw/` first for the Phase 3/3.5 ETL):

```bash
cd /home/deploy/projects/bg-realestate-intel
set -a; source /home/deploy/secrets/pocketbroker.env; set +a
cd backend
.venv/bin/alembic upgrade head          # create the schema
.venv/bin/python -m etl.run_etl          # prices + neighbourhoods (public data)
# .venv/bin/python -m etl.run_phase3     # builders + new buildings (needs uploaded data)
# .venv/bin/python -m etl.run_phase35    # ownership graph (needs uploaded data)
```

## 4. Install + start the backend service  (sudo)

```bash
sudo cp /home/deploy/projects/bg-realestate-intel/deploy/pocketbroker-api.service \
        /etc/systemd/system/pocketbroker-api.service
sudo systemctl daemon-reload
sudo systemctl enable --now pocketbroker-api
sudo systemctl status pocketbroker-api          # should be active (running)
curl -s http://127.0.0.1:8000/health            # {"status":"ok"}
```

## 5. Apply the nginx config  (sudo)

The server block is already in the source copy `/home/deploy/nginx-mvp.conf`.

```bash
sudo cp /home/deploy/nginx-mvp.conf /etc/nginx/sites-available/mvp
sudo nginx -t && sudo systemctl reload nginx
curl -s http://app.example.com/api/health   # {"status":"ok"} via the proxy
```

### 5a. SPA History-mode fallback (already in place — just verify)

The frontend router switched from hash routes (`/#/e/123`) to real paths
(`/e/123/some-company`) for SEO. Nginx must fall back to `index.html` for any
path that isn't a real file, so the Vue router can handle it client-side.

**No change is actually needed:** the `location /` block in the pocketbroker
server already uses `try_files $uri $uri/ /index.html;` (it was there for the
old hash router and is identical to what History mode requires). Just confirm
the `server { ... }` block of `/home/deploy/nginx-mvp.conf` (the one serving
`/var/www/pocketbroker/` at the document root) reads:

```nginx
location / {
    root /var/www/pocketbroker;
    try_files $uri $uri/ /index.html;
}
```

`$uri` is checked first, so real static files — `/robots.txt`,
`/sitemap.xml`, `/favicon.svg`, JS/CSS bundles — are served directly; only
unknown paths (entity/neighbourhood/company routes) fall back to
`index.html`. Verify (reload only if you actually edited the file):

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://app.example.com/e/000000000/test  # 200
curl -s -o /dev/null -w '%{content_type}\n' https://app.example.com/sitemap.xml    # application/xml
```

> ⚠️ `sitemap.xml` is generated into the web root at deploy time by
> `backend/scripts/generate_sitemap.py` (wired into `deploy.sh`). Until a
> deploy has run, `/sitemap.xml` does not exist on disk and the `try_files`
> fallback serves `index.html` (content-type `text/html`) — which is what
> `robots.txt` points crawlers at. Run a deploy to materialise it. This is the
> one genuinely outstanding step; nginx itself needs nothing.

## 6. HTTPS  (sudo)

Wildcard DNS already resolves the subdomain, so no DNS change is needed.

```bash
sudo certbot --nginx -d app.example.com
# Re-sync the source copy afterwards (certbot edits the LIVE file in place):
cp /etc/nginx/sites-available/mvp /home/deploy/nginx-mvp.conf
```

---

## Routine redeploys (after setup)

```bash
bash /home/deploy/projects/bg-realestate-intel/deploy.sh
```

Pulls, rebuilds the frontend, rsyncs it, installs backend deps, runs
`alembic upgrade head`, and restarts the service (the restart uses `sudo`).

---

## Backups

`deploy/db_backup.sh` takes a one-way, custom-format snapshot of a database into
`db/dumps/` (gitignored — dumps contain the private ownership/builder PII, so
never commit one or move it somewhere world-readable). It reads `DATABASE_URL`
from the env file; it never touches a remote DB.

```bash
# Back up PROD — run it ON the VPS:
ENV_FILE=/home/deploy/secrets/pocketbroker.env \
  bash /home/deploy/projects/bg-realestate-intel/deploy/db_backup.sh

# Back up your LOCAL dev DB — uses the default env path:
bash deploy/db_backup.sh
```

Dumps land at `db/dumps/bg_realestate_YYYYMMDD_HHMMSS.dump`. The script prunes
dumps older than `KEEP_DAYS` (default 14; `KEEP_DAYS=0` disables pruning).

**Schedule it (prod, daily at 03:00):** `crontab -e` on the VPS and add —

```cron
0 3 * * * ENV_FILE=/home/deploy/secrets/pocketbroker.env /home/deploy/projects/bg-realestate-intel/deploy/db_backup.sh >> /home/deploy/db_backup.log 2>&1
```

**Restore a dump** (DESTRUCTIVE — drops and recreates objects):

```bash
set -a; source /home/deploy/secrets/pocketbroker.env; set +a
DB_URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
pg_restore --clean --if-exists --no-owner -d "$DB_URL" db/dumps/bg_realestate_YYYYMMDD_HHMMSS.dump
```

> `db_backup.sh` is a local snapshot only. To copy your local dataset **up to
> prod**, use `deploy/db_push.sh` instead (it dumps, scp's, and restores over
> prod). The dumps live on the same disk as the DB — for disaster recovery, copy
> them off-server (another host or cloud storage).

> One-off manual dumps taken outside the script may live in `/home/deploy/backups/`
> (e.g. `bg_realestate_20260614_100312.dump`). That's not the scripted location —
> `db_backup.sh` always writes to `db/dumps/` — but check there too when hunting
> for an older snapshot.
