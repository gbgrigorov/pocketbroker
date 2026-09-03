#!/usr/bin/env bash
# Back up a PocketBroker Postgres database to a custom-format dump.
#
#   1. read DATABASE_URL from the env file (never hardcoded)
#   2. pg_dump (custom format, --no-owner --no-acl) into db/dumps/
#   3. prune dumps older than KEEP_DAYS
#
# Works on either side: run it locally (default env) to snapshot your dev DB, or
# run it ON THE VPS (ENV_FILE=/home/deploy/secrets/pocketbroker.env) to snapshot prod.
# This is a one-way SNAPSHOT — it never touches a remote DB. To copy local -> prod
# use db_push.sh; to restore, see "Backups" in deploy/SETUP.md.
#
# NOTE: dumps include the private ownership/builder PII, so db/dumps/ is gitignored.
# Never commit a dump or copy it somewhere world-readable.
#
# Env overrides:
#   ENV_FILE   path to the env file holding DATABASE_URL
#              (default: /home/deploy/secrets/pocketbroker.env)
#   KEEP_DAYS  delete dumps in db/dumps/ older than this many days
#              (default: 14; set to 0 to disable pruning)
set -euo pipefail

ENV_FILE="${ENV_FILE:-/home/deploy/secrets/pocketbroker.env}"
KEEP_DAYS="${KEEP_DAYS:-14}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DUMP_DIR="$ROOT/db/dumps"
mkdir -p "$DUMP_DIR"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: env file not found: $ENV_FILE" >&2
  echo "       Set ENV_FILE=/path/to/env (must define DATABASE_URL)." >&2
  exit 1
fi
set -a; source "$ENV_FILE"; set +a
if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL not set in $ENV_FILE" >&2
  exit 1
fi

# alembic-style URL (postgresql+psycopg://) -> libpq URL that pg_dump understands.
DB_URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
# Pull the database name out of the URL for the filename (strip query string too).
DB_NAME="${DB_URL##*/}"; DB_NAME="${DB_NAME%%\?*}"

STAMP="$(date +%Y%m%d_%H%M%S)"
DUMP_FILE="$DUMP_DIR/${DB_NAME}_${STAMP}.dump"

echo "==> Dumping '${DB_NAME}' -> ${DUMP_FILE}"
pg_dump -Fc --no-owner --no-acl -d "$DB_URL" -f "$DUMP_FILE"
echo "    $(du -h "$DUMP_FILE" | cut -f1) written."

# Sanity check: a custom-format dump must list its contents cleanly.
TABLES="$(pg_restore -l "$DUMP_FILE" | grep -c 'TABLE DATA' || true)"
echo "    ${TABLES} tables captured."

if [ "$KEEP_DAYS" -gt 0 ]; then
  echo "==> Pruning dumps older than ${KEEP_DAYS} days"
  find "$DUMP_DIR" -maxdepth 1 -name "${DB_NAME}_*.dump" -type f \
       -mtime "+${KEEP_DAYS}" -print -delete
fi

echo "==> Done. Restore with:"
echo "    pg_restore --clean --if-exists --no-owner -d \"\$DB_URL\" \"${DUMP_FILE}\""
