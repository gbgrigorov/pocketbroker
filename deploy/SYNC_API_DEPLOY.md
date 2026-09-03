# Deploy: research sync API — post-deploy steps (instructions for the AI agent on the VPS)

What this release adds, and the **two manual steps** it needs on prod. `deploy.sh`
cannot do either of them: one edits nginx, the other installs a secret.

You are the agent running on the VPS. Follow this top to bottom. Everything you
need is here. **Do not skip the verification commands** — one of them is the only
thing standing between a write-capable endpoint and the open internet.

## Hard rules for this procedure

- **Never print, echo, cat or log the token**, `DATABASE_URL`, or the contents of
  `/home/deploy/secrets/pocketbroker.env`. Not into the transcript, not into a file.
- **Never touch the `user` or `oauth_account` tables.** This release does not
  migrate them and neither do you.
- **Do the nginx step BEFORE the token step.** Between installing a valid token
  and closing the public route, the endpoint would be reachable from the internet
  by anyone holding that token. Closing the route first removes that window.
- If any verification below does not produce the expected output, **stop and
  report to Gabe** rather than continuing or improvising a fix.

---

## What this release adds

**Migration `b3c4d5e6f7a8`** — additive only:
- `research_request` gains three nullable columns: `report_md`, `notes`, `delivered_at`
- new table `sync_log` (audit trail of every push, dry runs included)

No tables dropped, no columns removed, no data rewritten. Safe on live data.

**New endpoints** under `/api/admin/sync/` — read research requests, and write
findings straight into the prod DB. Gated by an `X-Sync-Token` header checked
against the `RESEARCH_API_TOKEN` env var. **The gate fails closed:** while that
variable is unset, every one of these endpoints returns 403 to everybody. That is
why the deploy is safe before you do anything below.

Full design: `docs/superpowers/specs/2026-08-20-research-sync-api-design.md`.
Day-to-day usage: `deploy/SYNC_API.md`.

---

## Step 0 — Back up prod first (always)

```bash
cd ~/projects/bg-realestate-intel
ENV_FILE=/home/deploy/secrets/pocketbroker.env bash deploy/db_backup.sh
```

Writes a custom-format dump to `db/dumps/` (gitignored). Confirm the file exists
and is non-zero before continuing.

## Step 1 — Confirm the migration landed

`deploy.sh` runs `alembic upgrade head` automatically, so this should already be
done. Verify:

```bash
cd ~/projects/bg-realestate-intel/backend
set -a; source /home/deploy/secrets/pocketbroker.env; set +a
.venv/bin/alembic current
```

Expected: `b3c4d5e6f7a8 (head)`.

If it is not, run `.venv/bin/alembic upgrade head` and check again.

Then confirm the schema, without printing any connection string:

```bash
DB_URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
psql "$DB_URL" -tAc "SELECT to_regclass('sync_log')"
psql "$DB_URL" -tAc "SELECT count(*) FROM information_schema.columns
  WHERE table_name='research_request'
    AND column_name IN ('report_md','notes','delivered_at')"
```

Expected: `sync_log` and `3`.

## Step 2 — Confirm the gate is closed right now

Before changing anything, prove the endpoint is inert. Hit uvicorn directly:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/admin/sync/requests
```

Expected: `403` — because `RESEARCH_API_TOKEN` is not set yet. Anything other
than 403 means the fail-closed gate is not working: **stop and report.**

## Step 3 — Close the public route (do this BEFORE Step 4)

Find the site's nginx server block:

```bash
grep -rl "pocketbroker" /etc/nginx/sites-available/ /etc/nginx/conf.d/ 2>/dev/null
```

Inside the `server { ... }` block that serves the site, add:

```nginx
location ^~ /api/admin/sync {
    deny all;
}
```

Notes on that snippet, so you do not "improve" it into something weaker:
- `^~` stops nginx from letting a regex `location` take over the request.
- **No trailing slash** — a trailing slash would fail to match a bare
  `/api/admin/sync` request, which would then fall through to the general
  `/api/` proxy and reach the app.
- Position in the file does not matter: nginx picks the longest matching prefix,
  not the first one. Keep it next to the other `/api` blocks for readability.

Apply it:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

Verify from the VPS that the public route is dead:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://app.example.com/api/admin/sync/requests
```

Expected: `403`.

Also confirm you did not break the rest of the API:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://app.example.com/api/neighbourhoods
```

Expected: `200`. If this is not 200, **revert the nginx change, reload, and
report** — a broken public API is worse than an undeployed feature.

## Step 4 — Install the token

Generate it and append it to the secrets file **without printing it**:

```bash
python3 -c "import secrets; print(f'RESEARCH_API_TOKEN={secrets.token_urlsafe(32)}')" \
  | sudo tee -a /home/deploy/secrets/pocketbroker.env > /dev/null
```

The `> /dev/null` matters: `tee` would otherwise echo the secret into the
transcript. Confirm the variable is present **without revealing its value**:

```bash
grep -c '^RESEARCH_API_TOKEN=' /home/deploy/secrets/pocketbroker.env
```

Expected: `1`. If it is `2` or more, an old value is shadowing the new one —
report to Gabe rather than editing the file blind.

Restart so the app picks it up:

```bash
sudo systemctl restart pocketbroker-api
sudo systemctl is-active pocketbroker-api
```

Expected: `active`.

## Step 5 — Verify the gate now works, both ways

Wrong token, straight to uvicorn — must still be refused:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -H 'X-Sync-Token: definitely-wrong' http://127.0.0.1:8000/api/admin/sync/requests
```

Expected: `403`.

Correct token — read it from the env file into a shell variable, never onto the
screen:

```bash
set -a; source /home/deploy/secrets/pocketbroker.env; set +a
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "X-Sync-Token: ${RESEARCH_API_TOKEN}" http://127.0.0.1:8000/api/admin/sync/requests
```

Expected: `200`.

And the public route is still dead even with a valid token:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "X-Sync-Token: ${RESEARCH_API_TOKEN}" \
  https://app.example.com/api/admin/sync/requests
```

Expected: `403`. **If this returns 200, the nginx block is not effective —
remove the token from the env file, restart the service, and report immediately.**

## Step 6 — Confirm nothing else moved

```bash
psql "$DB_URL" -tAc 'SELECT count(*) FROM "user"'
psql "$DB_URL" -tAc 'SELECT count(*) FROM entity'
psql "$DB_URL" -tAc 'SELECT count(*) FROM research_request'
```

Compare against the pre-deploy backup from Step 0. This release writes no data,
so all three must be unchanged.

---

## Step 7 — Report back to Gabe

Do **not** send him the token. Tell him:

1. Which steps passed, with the actual status codes you observed.
2. That the token is installed in `/home/deploy/secrets/pocketbroker.env`, and that
   he retrieves it himself from the MacBook with:

   ```bash
   ssh deploy@app.example.com "grep '^RESEARCH_API_TOKEN=' /home/deploy/secrets/pocketbroker.env"
   ```

   He pastes that value into the repo's local `.env`. The secret then exists in
   exactly two places and has never passed through a transcript.
3. The three row counts from Step 6.

Once he has the token locally, he verifies end-to-end from the MacBook with
`python3 scripts/pb.py requests` — which tunnels to uvicorn and bypasses nginx.

## If you need to roll this back

The feature is inert without the token, so rollback is: remove the
`RESEARCH_API_TOKEN=` line from `/home/deploy/secrets/pocketbroker.env` and
`sudo systemctl restart pocketbroker-api`. Every sync endpoint returns to 403.

Leave the nginx block and the migration in place — both are harmless, and the
migration is additive.
