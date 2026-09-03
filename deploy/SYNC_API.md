# Research Sync API — MacBook → production

Replaces the CSV + `scp` + VPS-Claude procedure in `ENTITY_PUSH.md`. Findings
are pushed straight into the production database over an SSH tunnel.

> **First deploy?** The server-side steps are scripted for the VPS agent in
> [`SYNC_API_DEPLOY.md`](SYNC_API_DEPLOY.md) — hand it that file. The section
> below is the same setup written for a human.

## One-time setup

### 1. Close the route to the internet (on the VPS)

Do this **before** installing the token: between a valid token existing and the
public route being closed, the endpoint would be reachable from the internet by
anyone holding it.

In the nginx server block for the site:

```nginx
location ^~ /api/admin/sync {
    deny all;
}
```

`^~` stops a regex `location` from taking the request instead, and the missing
trailing slash is deliberate — with one, a bare `/api/admin/sync` would fall
through to the general `/api/` proxy. Position in the file is irrelevant: nginx
matches the longest prefix, not the first.

Then `sudo nginx -t && sudo systemctl reload nginx`.

Verify from the MacBook — this must return 403 from nginx, not a JSON error:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://app.example.com/api/admin/sync/requests
# 403
```

`pb` does not go through nginx: it tunnels to uvicorn on 127.0.0.1:8000.

### 2. Generate and install the token (on the VPS)

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Add the value to `/home/deploy/secrets/pocketbroker.env` as `RESEARCH_API_TOKEN=…`
and restart the service:

```bash
sudo systemctl restart pocketbroker-api
```

Put the **same** value in the local repo `.env` as `RESEARCH_API_TOKEN`, plus
`VPS_HOST`, `VPS_USER`, `VPS_PORT`.

Until this variable is set the endpoints fail closed — every request gets 403,
including yours.

### 3. Migrate the schema

`deploy.sh` runs `alembic upgrade head`, which applies `b3c4d5e6f7a8`
(`sync_log` + the `research_request` delivery columns).

## Daily use

```bash
python3 scripts/pb.py requests              # what is waiting
python3 scripts/pb.py claim 7               # new -> in_progress
python3 scripts/pb.py prod 175376051        # what prod already holds
python3 scripts/pb.py push 7 data/bundles/175376051_20260820.json
python3 scripts/pb.py push 7 data/bundles/175376051_20260820.json --apply
```

`push` is a **dry run** unless `--apply` is given: the server applies the bundle
in a transaction, reports every field it would change, and rolls back.

## Bundle format

See §6 of `docs/superpowers/specs/2026-08-20-research-sync-api-design.md`.
Entities are addressed by ЕИК (companies) or `person_key` (persons) — never by
database id. Capital crosses as `capital_eur`.

Bundles are written to `data/bundles/<eik>_<stamp>.json` and are the record of
what was delivered; re-pushing one is a no-op.

## Safety properties

- The sync endpoints never read or write `user` or `oauth_account`.
- An unset `RESEARCH_API_TOKEN` rejects every request (fails closed).
- A bundle is all-or-nothing: an unresolvable reference returns 422 and writes
  nothing.
- Every push, dry runs included, appends a row to `sync_log`.
