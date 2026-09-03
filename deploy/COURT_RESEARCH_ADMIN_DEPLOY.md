# Deploy: court-research orders + admin page (PR #15)

What this release adds to the database and the one manual step it needs on prod.

## DB change

A single **additive** migration — `backend/alembic/versions/d4e5f6a7b8c9_court_research_order_fields.py`
— adds 7 nullable / server-defaulted columns to `research_request`:

```
order_type ('lead' default) · scope · search_type · network_depth
· entity_count · price_eur · expedited (false default)
```

No tables dropped, no columns removed, no data rewritten — existing lead rows
backfill to `order_type='lead'`, `expedited=false`. Safe to run on live data; the
running API keeps working before and after.

The admin page adds **no schema** — it reuses `research_request` and the existing
`user` table (gated on the built-in `is_superuser` flag).

---

## Steps

### 0. Back up prod first (always)
On the VPS, snapshot the live DB before migrating:
```bash
cd ~/<app-root> && ENV_FILE=/home/deploy/secrets/pocketbroker.env bash deploy/db_backup.sh
```
Writes a custom-format dump to `db/dumps/` (gitignored). Restore, if ever needed:
```bash
pg_restore --clean --if-exists --no-owner -d "$DB_URL" db/dumps/<file>.dump
```

### 1. Migrate (automatic on deploy)
`deploy.sh` already runs `alembic upgrade head` (deploy.sh:32-34), so merging PR #15
to `main` → GitHub Actions deploy applies the migration. To run it by hand instead:
```bash
cd ~/<app-root>/backend
set -a; source /home/deploy/secrets/pocketbroker.env; set +a
.venv/bin/alembic upgrade head        # -> d4e5f6a7b8c9
```

### 2. Grant yourself admin (one-time, manual)
There is no UI to set `is_superuser`; flag your prod account directly. Find it first
if unsure (e.g. `deploy/count_users.sh`, or query by name):
```bash
set -a; source /home/deploy/secrets/pocketbroker.env; set +a
DB_URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
psql -d "$DB_URL" -c "SELECT id, email, name, is_superuser FROM \"user\";"
psql -d "$DB_URL" -c "UPDATE \"user\" SET is_superuser = true WHERE email = '<your-prod-email>';"
```
(Dev was already granted: `dev@example.com`, id 2.)

### 3. Verify
```bash
# anon -> 401, non-admin -> 403, admin (with a superuser JWT) -> 200
curl -s -o /dev/null -w '%{http_code}\n' https://<prod>/api/admin/users
```
Then sign in as the admin account in the app: the **Admin** link appears in the
sidebar, `/admin` loads, and the Requests/Users tables populate.

---

## Rollback
Code: revert the merge. DB: the migration is additive, so a downgrade is optional and
safe to leave in place. If you must:
```bash
.venv/bin/alembic downgrade -1        # drops the 7 columns (loses court-order metadata)
```
Do **not** downgrade if any `order_type='court_research'` rows exist that you want to keep.

## Note on `db_push.sh`
Do **not** use `deploy/db_push.sh` for this — it does a full `pg_restore --clean` and
**wipes prod users**. This release only needs the migration (step 1) + the grant (step 2).
