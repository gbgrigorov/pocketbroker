# Research Sync API — design

**Date:** 2026-08-20
**Status:** approved, ready for implementation plan

Replace the manual `deploy/ENTITY_PUSH.md` procedure (CSV dump → `scp` → a Claude
session on the VPS) with an HTTP API the MacBook talks to directly: read the new
research requests off production, do the research locally, push the findings
straight into the production database.

---

## 1. Problem

Research requests are submitted by visitors and land in the production
`research_request` table. Research happens on the MacBook (Papagal, legalacts,
CAPTCHA work, crawlers). Getting the results back to production today means a
hand-run CSV export, an `scp`, and a second Claude session on the VPS applying a
`DELETE + reload` mirror of seven tables. It is slow, manual, and the mirror is
destructive.

## 2. Decisions

| Question | Decision |
|---|---|
| Scope | The research-request loop: fetch requests, push findings. Bulk/crawl data uses the same bundle endpoint, unattached to a request. |
| Data flow | **Write straight to prod.** Production is the write target for entity/research data. |
| Local DB | Becomes a dev sandbox. It will drift from prod; local tests use fixtures. |
| Payload | **One bundle per request**, applied in a single transaction. |
| Auth | Dedicated `RESEARCH_API_TOKEN` **and** no public route (SSH tunnel). |
| Lifecycle | `new → in_progress → delivered`, flipped by the API. |
| `ENTITY_PUSH.md` | **Retired.** The API becomes the only write path. |
| Deliverable | Bundle carries `report_md` + `notes`, stored on `research_request`. |
| Safety | **Dry-run by default**; `--apply` commits. |
| Read-back | Yes — read-only lookup endpoints so a push can be diffed first. |

## 3. Architecture

New package `backend/app/sync/`:

- `router.py` — HTTP layer, auth dependency, request/response handling
- `upsert.py` — pure DB functions, no FastAPI imports; independently testable
- `schemas.py` — Pydantic models for the bundle and the diff report

`backend/app/routes.py` is already 1,225 lines and is not extended.

### Shared upsert helpers

`etl/entities.py` already implements get-or-create-by-natural-key
(`entity_for_builder`, `entity_for_person`, edge upsert). Those helpers are
**moved to `backend/app/entities.py`** (they depend only on `app.models` and
`app.slugs`), with `etl/entities.py` re-exporting them so the ETL is unchanged.
`_norm_name` moves from `etl/load_phase3.py` to `app/names.py` alongside them.

Rationale: the API and the ETL then share one implementation, and the deployed
API does not depend on the ETL package. Dependency direction becomes
`etl → app`, never the reverse.

## 4. Transport & auth

- **Nginx returns `deny all` for `/api/admin/sync/`** — the path is unreachable
  from the internet. No IP allowlist (a home IP is dynamic and would break).
- **The CLI opens its own SSH tunnel** (`ssh -N -L 8787:127.0.0.1:8000
  deploy@<host>`) and calls `127.0.0.1:8787`, reaching uvicorn behind nginx. The
  tunnel is torn down when the command exits.
- **`X-Sync-Token` header is required regardless** — new `RESEARCH_API_TOKEN` in
  `/home/deploy/secrets/pocketbroker.env`, mirroring the existing `X-Admin-Token`
  pattern. Compared with `secrets.compare_digest`. **Fails closed when the env
  var is unset**, so a misconfigured deploy cannot leave the endpoint open.

An attacker needs SSH access *and* the token. Neither the token nor the VPS host
is committed to git.

## 5. Endpoints

All under `/api/admin/sync/`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/requests?status=new&limit=` | Requests, newest first, with the `in_db` / `court_checked_at` coverage flags the admin inbox already derives |
| `POST` | `/requests/{id}/claim` | `new` → `in_progress` |
| `GET` | `/entities?eik=X&eik=Y` | What prod holds per ЕИК: entity fields, edge/signal counts, last court check |
| `POST` | `/requests/{id}/findings?dry_run=` | Apply a bundle and flip the request to `delivered`. `dry_run` defaults to **true** |
| `POST` | `/bundle?dry_run=` | Same bundle, unattached to a request — the replacement for `ENTITY_PUSH.md` |

## 6. The bundle

```jsonc
{
  "entities":  [{ "kind": "company", "eik": "175376051", "name": "…",
                  "legal_form": "ООД", "status": "…", "capital_eur": 5000,
                  "founded_year": 2008, "address": "…", "source": "papagal" }],
  "builder":   { "eik": "…", "ksb_category": "…", "insolvency_flag": false },
  "edges":     [{ "src": {"eik": "…"}, "dst": {"person_key": "…"},
                  "relation": "ownership", "share_pct": 50,
                  "valid_from": "2008-01-01" }],
  "signals":   [{ "url": "…", "matched_name": "…", "tier": "official",
                  "source_type": "registry", "match_confidence": "eik" }],
  "court_checks": [{ "eik": "…", "method": "eik", "acts_found": 3,
                     "checked_at": "2026-08-20T10:00:00Z" }],
  "report_md": "# Findings\n…",
  "notes":     "internal note"
}
```

Edges reference entities by **natural key** (`eik` / `person_key`), never by id.
The server resolves them to production ids, including entities created earlier
in the same bundle. This is what makes writing straight to prod safe — local ids
never leave the MacBook.

### 6.1 Where a bundle comes from

A research session assembles the bundle as JSON and writes it to
`data/bundles/<eik>_<stamp>.json`, then pushes it with `pb push`. That file is
the record of what was delivered and can be re-pushed verbatim.

The local ETL loaders are unchanged and still write the local sandbox DB — they
are just no longer the path to production. Nothing auto-converts a local DB row
into a bundle; if that turns out to be wanted, an exporter is a later addition.

## 7. Idempotency rules

Capital is carried as **`capital_eur`** and converted at the fixed peg by the
shared helper — the column is `capital_bgn`, the input is euro.

**Core rule: enrich, don't erase.** A `null` or omitted field in the bundle never
overwrites a non-null value in production. Only explicitly-provided fields are
written. This makes re-pushing a partial bundle safe.

| Object | Key | Behaviour |
|---|---|---|
| Company entity | `eik` (unique) | upsert, enrich-don't-erase (`app.entities.entity_for_company`) |
| Person entity | `person_key` (required) | upsert; a person without a key is a **validation error**, not a silent new node |
| Builder | `eik` (unique) | upsert, links `entity_id` |
| Edge | `src`/`dst` natural keys resolved to ids, then `(src, dst, relation, valid_from)` | matches the existing unique constraint |
| Signal | `(url, matched_name)` | matches the existing unique constraint |
| Court check | `(eik, source_site, checked_at)` exact match → skip | append-only log; exact-match skip makes retries idempotent |

A person entity **must** carry `person_key`. The alternative — falling back to a
fuzzy name match — risks merging two different people in production, and
creating a keyless node risks a duplicate on every re-push. Failing loudly is
the only safe option. The existing `entity_for_person` helper keeps its
conservative behaviour unchanged; the validation lives in the sync layer.

Two rules carried over from past incidents:

- Signals key on `(url, matched_name)` and resolve `entity_id` **per entity** —
  never by URL substring. One court `actId` legitimately belongs to many
  companies' ЕИКs; substring matching clobbered ДИНЕСО once.
- Bundle validation **warns** (does not fail) when a `kind: "person"` entity
  carries a `person_key` whose prefix is a known company ЕИК. That is Papagal's
  corporate-shareholder shape and is easy to mis-type silently.

## 8. Dry run

The endpoint runs the entire upsert inside a transaction, builds a per-table
diff, then rolls back. Identical code path to a real apply — the only difference
is the final `commit()`.

Report shape:

```jsonc
{
  "dry_run": true,
  "tables": { "entity": {"created": 3, "updated": 1, "unchanged": 12, "skipped": 0}, … },
  "changes": [ { "table": "entity", "key": "175376051", "field": "founded_year",
                 "from": null, "to": 2008 } ],
  "warnings": [ "entity person_key 175376051-2 looks like a corporate shareholder" ]
}
```

`changes` is capped at the first N entries; the counts are always complete.

## 9. Migration

`down_revision = 'a1b2c3d4e5f7'` (current head, `court_check_log`).

- `research_request.report_md` TEXT NULL
- `research_request.notes` TEXT NULL
- `research_request.delivered_at` TIMESTAMP NULL
- new table `sync_log` — `id, request_id (FK research_request.id, nullable),
  action, dry_run BOOLEAN, summary JSONB, created_at` — audit trail of every
  push, dry-runs included
- `research_request.status` is already free-text `String`; `in_progress` and
  `delivered` need no DDL

## 10. Client — `scripts/pb.py`

Standard library only (`urllib`, `json`, `subprocess`). No packages installed on
the MacBook or the VPS.

```
pb requests [--status new]         # what is waiting
pb claim <id>                      # new -> in_progress
pb prod <eik> [<eik>...]           # what prod already holds
pb push <id> bundle.json           # DRY RUN, prints the diff
pb push <id> bundle.json --apply   # commits
pb push-bulk bundle.json           # unattached bundle
```

Reads `RESEARCH_API_TOKEN` and the VPS host from `.env`, opens the SSH tunnel for
the duration of the command, and never prints the token or the host.

## 11. Invariants

- **No sync code path may read or write `user` or `oauth_account`.** Asserted in
  tests: the `user` row count is unchanged after every push.
- Auth fails closed when `RESEARCH_API_TOKEN` is unset.
- A dry run leaves zero rows behind.
- Pushing the same bundle twice produces identical database state.

## 12. Tests

Pytest, existing `backend/tests/conftest.py`, written before the implementation.

- auth fails closed when the env var is unset; wrong token → 403; anonymous → 403
- dry run leaves zero rows behind
- double-push produces identical state (idempotency)
- edges resolve against entities created earlier in the same bundle
- nulls and omitted fields do not erase existing prod values
- status transitions `new → in_progress → delivered`, `delivered_at` set
- `user` row count unchanged after every push
- a bundle that fails validation mid-way rolls back completely
- `sync_log` records both dry-runs and applies

## 13. Rollout

1. Local suite green.
2. `deploy.sh` (runs `alembic upgrade head` on prod).
3. Set `RESEARCH_API_TOKEN` in `/home/deploy/secrets/pocketbroker.env`; restart
   `pocketbroker-api`.
4. Add the nginx `deny all` block for `/api/admin/sync/`; reload nginx.
5. Smoke test: `pb requests`, then a dry-run push against a real request.
6. Stamp `deploy/ENTITY_PUSH.md` deprecated with a pointer to `pb push-bulk`.

## 14. Out of scope

Emailing requesters when findings land · two-way sync · pulling prod back to
local · a production admin UI for editing findings · migrating existing local
entity data to prod (a one-off `push-bulk` after rollout, not part of the build).
