#!/usr/bin/env bash
# Push the LOCAL Postgres database to PRODUCTION (local -> prod).
#
#   1. pg_dump the local DB (custom format) into db/dumps/
#   2. scp the dump to the VPS
#   3. pg_restore --clean over the prod DB (DESTRUCTIVE: replaces prod data)
#
# ⚠️ PROD NOW HAS LIVE USERS — this full replace WIPES the user/oauth_account
#    tables. For entity/research data use deploy/ENTITY_PUSH.md instead.
#
# Schema migrations are handled separately by `alembic upgrade head` inside
# deploy.sh. This script moves DATA. Run it only when you intentionally want the
# prod DB to mirror your local dataset (e.g. after a fresh local Phase 3/3.5 scrape).
#
# Env overrides:
#   LOCAL_DB   local database name           (default: bg_realestate)
#   VPS_HOST   ssh host                       (default: app.example.com)
#   VPS_USER   ssh user                       (default: mvp)
#   VPS_PORT   ssh port                       (default: 22)
#   PROD_ENV   path to prod env on the VPS    (default: /home/deploy/secrets/pocketbroker.env)
#              (DATABASE_URL is read from there, never hardcoded)
set -euo pipefail

LOCAL_DB="${LOCAL_DB:-bg_realestate}"
VPS_HOST="${VPS_HOST:-app.example.com}"
VPS_USER="${VPS_USER:-mvp}"
VPS_PORT="${VPS_PORT:-22}"
PROD_ENV="${PROD_ENV:-/home/deploy/secrets/pocketbroker.env}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DUMP_DIR="$ROOT/db/dumps"
mkdir -p "$DUMP_DIR"

STAMP="$(date +%Y%m%d_%H%M%S)"
DUMP_FILE="$DUMP_DIR/${LOCAL_DB}_${STAMP}.dump"
REMOTE_FILE="/home/deploy/${LOCAL_DB}_${STAMP}.dump"

echo "==> 1/3 Dumping local DB '${LOCAL_DB}' -> ${DUMP_FILE}"
pg_dump -Fc --no-owner --no-acl -d "$LOCAL_DB" -f "$DUMP_FILE"
echo "    $(du -h "$DUMP_FILE" | cut -f1) written."

echo ""
echo "==> About to OVERWRITE the production database on ${VPS_USER}@${VPS_HOST}."
echo "    pg_restore --clean --if-exists will DROP and recreate objects from this dump."
read -r -p "    Type the DB name ('${LOCAL_DB}') to confirm, anything else aborts: " CONFIRM
if [ "$CONFIRM" != "$LOCAL_DB" ]; then
  echo "    Aborted. Local dump kept at ${DUMP_FILE}; prod untouched."
  exit 1
fi

echo ""
echo "==> 2/3 Copying dump to ${VPS_USER}@${VPS_HOST}:${REMOTE_FILE}"
scp -P "$VPS_PORT" "$DUMP_FILE" "${VPS_USER}@${VPS_HOST}:${REMOTE_FILE}"

echo ""
echo "==> 3/3 Restoring on prod (DATABASE_URL sourced from ${PROD_ENV})"
ssh -p "$VPS_PORT" "${VPS_USER}@${VPS_HOST}" bash -s <<REMOTE
set -euo pipefail
set -a; source "${PROD_ENV}"; set +a
# alembic-style URL (postgresql+psycopg://) -> libpq URL for pg_restore
DB_URL="\${DATABASE_URL/postgresql+psycopg:/postgresql:}"
pg_restore --clean --if-exists --no-owner -d "\$DB_URL" "${REMOTE_FILE}"
rm -f "${REMOTE_FILE}"
echo "    Restore complete; remote dump removed."
REMOTE

echo ""
echo "==> Done. Prod now mirrors local '${LOCAL_DB}'. Local dump kept at ${DUMP_FILE}."
