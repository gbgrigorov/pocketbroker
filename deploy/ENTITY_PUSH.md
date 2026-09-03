# Entity Push — local → prod, without touching users

> ## ⛔️ DEPRECATED — do not run this
>
> Production is now written directly by the sync API (`deploy/SYNC_API.md`).
> The procedure below **full-mirrors** the entity tables from local: it runs
> `DELETE FROM entity` and reloads from CSV, which would **erase every finding
> pushed through the API** since the last local scrape.
>
> Use `python3 scripts/pb.py push-bulk <bundle.json>` for bulk data instead.
>
> Kept only as a record of the pre-API procedure.

Moves the **entity/research data** (ownership graph, builders, signals, new
buildings) from the local DB to production by mirroring those tables.
**Never touches `user`, `oauth_account`, `price_snapshot`, or any other table.**

Use this instead of `deploy/db_push.sh` — that script does a full
`pg_restore --clean` and **wipes the live prod users**.

How it works: prod never writes to the entity tables (only local research
does), so we can safely delete + reload them wholesale inside one transaction.
This carries new rows, in-place enrichments (no `updated_at` column exists to
diff on), and deletions alike. The tables are small; the whole load is atomic —
the running API never sees empty tables (MVCC), and any error rolls everything
back.

| Tables | Treatment |
|---|---|
| `entity`, `builder`, `entity_edge`, `entity_signal`, `new_building`, `new_building_source`, `court_check` | full mirror (delete + reload) |
| `city`, `neighbourhood` | top-up only (`ON CONFLICT (id) DO NOTHING`) — referenced by prod `price_snapshot`, never deleted |
| `user`, `oauth_account`, everything else | **untouched** |

Schema migrations are NOT handled here. If models changed, deploy first
(`deploy.sh` runs `alembic upgrade head` on prod); step 2 aborts on version
mismatch.

---

## Part 1 — Local: export the dump (copy-paste)

```bash
cd ~/Dev/bg-realestate-intel
STAMP=$(date +%Y%m%d_%H%M)
DIR="db/dumps/entity_dump_${STAMP}"
mkdir -p "$DIR"

for t in city neighbourhood entity builder entity_edge entity_signal new_building new_building_source court_check; do
  psql -d bg_realestate -c "\copy (SELECT * FROM ${t} ORDER BY id) TO '${DIR}/${t}.csv' WITH (FORMAT csv)"
done

psql -d bg_realestate -tAc "SELECT version_num FROM alembic_version" > "$DIR/alembic_version.txt"

psql -d bg_realestate -tA -F': ' -c "
  SELECT 'entity', count(*) FROM entity
  UNION ALL SELECT 'builder', count(*) FROM builder
  UNION ALL SELECT 'entity_edge', count(*) FROM entity_edge
  UNION ALL SELECT 'entity_signal', count(*) FROM entity_signal
  UNION ALL SELECT 'new_building', count(*) FROM new_building
  UNION ALL SELECT 'new_building_source', count(*) FROM new_building_source
  UNION ALL SELECT 'court_check', count(*) FROM court_check
  ORDER BY 1" > "$DIR/counts.txt"
cat "$DIR/counts.txt"

tar czf "db/dumps/entity_dump_${STAMP}.tar.gz" -C db/dumps "entity_dump_${STAMP}"
echo "Now run:  scp db/dumps/entity_dump_${STAMP}.tar.gz deploy@app.example.com:~/projects/bg-realestate-intel/db/dump/"
```

Run the printed `scp` command, then start a Claude session on the VPS and tell
it: *"Apply the entity dump in ~/projects/bg-realestate-intel/db/dump/entity_dump_<stamp>.tar.gz
following deploy/ENTITY_PUSH.md Part 2."* (Paste Part 2 if the repo isn't on the server.)

---

## Part 2 — Server: apply the dump (instructions for Claude on the VPS)

You are applying a data-only entity sync. **Do not touch the `user` or
`oauth_account` tables under any circumstances. Do not run `db_push.sh` or
`pg_restore`.** Everything below is the complete procedure.

### 2.1 Unpack and connect

```bash
cd ~/projects/bg-realestate-intel/db/dump
tar xzf entity_dump_*.tar.gz
cd entity_dump_*/

set -a; source /home/deploy/secrets/pocketbroker.env; set +a
DB_URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"   # alembic URL -> libpq URL
```

Never print `DATABASE_URL` / `DB_URL` or the contents of the env file.

### 2.2 Preconditions — abort if any fails

```bash
# Schema versions must match (CSV column order depends on it)
psql "$DB_URL" -tAc "SELECT version_num FROM alembic_version"
cat alembic_version.txt
# -> must be identical. If not: STOP, tell Gabe to run deploy.sh first.

# Record the live user count (must be unchanged at the end)
psql "$DB_URL" -tAc 'SELECT count(*) FROM "user"'
```

### 2.3 Build `apply.sql`

Write the file below into the dump directory, replacing each `<N_*>`
placeholder with the matching number from `counts.txt`:

```sql
BEGIN;

-- Reference top-ups: insert rows prod is missing, never delete/update
CREATE TEMP TABLE staging_city (LIKE city INCLUDING DEFAULTS) ON COMMIT DROP;
\copy staging_city FROM 'city.csv' WITH (FORMAT csv)
INSERT INTO city SELECT * FROM staging_city ON CONFLICT (id) DO NOTHING;

CREATE TEMP TABLE staging_neighbourhood (LIKE neighbourhood INCLUDING DEFAULTS) ON COMMIT DROP;
\copy staging_neighbourhood FROM 'neighbourhood.csv' WITH (FORMAT csv)
INSERT INTO neighbourhood SELECT * FROM staging_neighbourhood ON CONFLICT (id) DO NOTHING;

-- Mirror the entity tables: delete in reverse-FK order…
DELETE FROM court_check;
DELETE FROM new_building_source;
DELETE FROM new_building;
DELETE FROM entity_signal;
DELETE FROM entity_edge;
DELETE FROM builder;
DELETE FROM entity;

-- …reload in forward-FK order
\copy entity FROM 'entity.csv' WITH (FORMAT csv)
\copy builder FROM 'builder.csv' WITH (FORMAT csv)
\copy entity_edge FROM 'entity_edge.csv' WITH (FORMAT csv)
\copy entity_signal FROM 'entity_signal.csv' WITH (FORMAT csv)
\copy new_building FROM 'new_building.csv' WITH (FORMAT csv)
\copy new_building_source FROM 'new_building_source.csv' WITH (FORMAT csv)
\copy court_check FROM 'court_check.csv' WITH (FORMAT csv)

-- Bump sequences so future prod inserts can't collide with imported ids
SELECT setval(pg_get_serial_sequence('city','id'),                COALESCE((SELECT max(id) FROM city), 1));
SELECT setval(pg_get_serial_sequence('neighbourhood','id'),       COALESCE((SELECT max(id) FROM neighbourhood), 1));
SELECT setval(pg_get_serial_sequence('entity','id'),              COALESCE((SELECT max(id) FROM entity), 1));
SELECT setval(pg_get_serial_sequence('builder','id'),             COALESCE((SELECT max(id) FROM builder), 1));
SELECT setval(pg_get_serial_sequence('entity_edge','id'),         COALESCE((SELECT max(id) FROM entity_edge), 1));
SELECT setval(pg_get_serial_sequence('entity_signal','id'),       COALESCE((SELECT max(id) FROM entity_signal), 1));
SELECT setval(pg_get_serial_sequence('new_building','id'),        COALESCE((SELECT max(id) FROM new_building), 1));
SELECT setval(pg_get_serial_sequence('new_building_source','id'), COALESCE((SELECT max(id) FROM new_building_source), 1));
SELECT setval(pg_get_serial_sequence('court_check','id'),         COALESCE((SELECT max(id) FROM court_check), 1));

-- Verify row counts against the local export; any mismatch rolls everything back
DO $$
DECLARE bad text;
BEGIN
  SELECT string_agg(format('%s: got %s, expected %s', t, actual, expected), '; ')
  INTO bad
  FROM (VALUES
    ('entity',              (SELECT count(*) FROM entity),              <N_ENTITY>),
    ('builder',             (SELECT count(*) FROM builder),             <N_BUILDER>),
    ('entity_edge',         (SELECT count(*) FROM entity_edge),         <N_ENTITY_EDGE>),
    ('entity_signal',       (SELECT count(*) FROM entity_signal),       <N_ENTITY_SIGNAL>),
    ('new_building',        (SELECT count(*) FROM new_building),        <N_NEW_BUILDING>),
    ('new_building_source', (SELECT count(*) FROM new_building_source), <N_NEW_BUILDING_SOURCE>),
    ('court_check',         (SELECT count(*) FROM court_check),         <N_COURT_CHECK>)
  ) AS v(t, actual, expected)
  WHERE actual <> expected;
  IF bad IS NOT NULL THEN
    RAISE EXCEPTION 'Row count mismatch — rolling back: %', bad;
  END IF;
END $$;

COMMIT;
```

### 2.4 Apply

```bash
psql -v ON_ERROR_STOP=1 "$DB_URL" -f apply.sql
```

Note: `setval()` is not transactional — if the transaction rolls back after a
count mismatch, sequences may stay bumped. That is harmless (ids just skip
ahead); fix the cause and re-run, the procedure is idempotent.

### 2.5 Verify

```bash
# User count — must equal the number recorded in 2.2
psql "$DB_URL" -tAc 'SELECT count(*) FROM "user"'

# Row counts — must match counts.txt
psql "$DB_URL" -tA -F': ' -c "
  SELECT 'entity', count(*) FROM entity
  UNION ALL SELECT 'builder', count(*) FROM builder
  UNION ALL SELECT 'entity_edge', count(*) FROM entity_edge
  UNION ALL SELECT 'entity_signal', count(*) FROM entity_signal
  UNION ALL SELECT 'new_building', count(*) FROM new_building
  UNION ALL SELECT 'new_building_source', count(*) FROM new_building_source
  UNION ALL SELECT 'court_check', count(*) FROM court_check
  ORDER BY 1"
cat counts.txt
```

Then clean up: `rm -rf ~/projects/bg-realestate-intel/db/dump/entity_dump_*`
(dump + extracted dir; the local copy in `db/dumps/` is the archive of record).

---

## Part 3 — Final checks (Gabe)

- [ ] Prod row counts (printed in 2.5) match `counts.txt`
- [ ] `user` count unchanged — log in with an existing account on https://app.example.com
- [ ] A newly-researched entity shows up in entity search on the live site
- [ ] Re-running the whole procedure is safe (idempotent delete + reload)
