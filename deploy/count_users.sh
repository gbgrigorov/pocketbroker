#!/usr/bin/env bash
# Print how many user accounts exist in the PRODUCTION database.
#
# Reads DATABASE_URL from the prod env file (never hardcoded), converts the
# SQLAlchemy URL to a libpq URL, and counts rows in the "user" table.
#
# Usage:
#   ./deploy/count_users.sh           # prints just the total (e.g. 42)
#   ./deploy/count_users.sh -v        # prints total / active / verified breakdown
#
# Env overrides:
#   PROD_ENV   path to prod env file   (default: /home/deploy/secrets/pocketbroker.env)
set -euo pipefail

PROD_ENV="${PROD_ENV:-/home/deploy/secrets/pocketbroker.env}"

if [ ! -f "$PROD_ENV" ]; then
  echo "error: env file not found: $PROD_ENV" >&2
  exit 1
fi

set -a; source "$PROD_ENV"; set +a

if [ -z "${DATABASE_URL:-}" ]; then
  echo "error: DATABASE_URL not set in $PROD_ENV" >&2
  exit 1
fi

# alembic-style URL (postgresql+psycopg://) -> libpq URL for psql
DB_URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"

if [ "${1:-}" = "-v" ]; then
  psql "$DB_URL" -tAF $'\t' -c \
    "SELECT count(*) AS total,
            count(*) FILTER (WHERE is_active)   AS active,
            count(*) FILTER (WHERE is_verified) AS verified
     FROM \"user\";" \
    | awk -F'\t' '{printf "total: %s\nactive: %s\nverified: %s\n", $1, $2, $3}'
else
  psql "$DB_URL" -tAc 'SELECT count(*) FROM "user";'
fi
