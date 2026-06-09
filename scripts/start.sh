#!/usr/bin/env bash
#
# One-command startup for PosyHub on Termux + proot Ubuntu (PostgreSQL).
#
# Runs every step automatically, in order:
#   1. start the PostgreSQL cluster (if not already running)
#   2. wait until Postgres accepts connections
#   3. ensure the app role + database exist (idempotent)
#   4. export DATABASE_URL
#   5. migrate data from SQLite the first time only (no-op afterwards)
#   6. launch the Flask app
#
# Usage:
#   ./scripts/start.sh
#
# Anything below can be overridden from the environment, e.g.:
#   PORT=8000 DB_PASSWORD=secret ./scripts/start.sh
#
set -euo pipefail

# --- config (override via env) ------------------------------------------------
PG_VERSION="${PG_VERSION:-16}"
PG_DATA="${PG_DATA:-/var/lib/postgresql/${PG_VERSION}/main}"
PG_LOG="${PG_LOG:-/tmp/pg.log}"
PG_BIN="/usr/lib/postgresql/${PG_VERSION}/bin"

DB_NAME="${DB_NAME:-posyhub}"
DB_USER="${DB_USER:-posyhub}"
DB_PASSWORD="${DB_PASSWORD:-posyhub}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

# Repo root = parent of this script's directory.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# DATABASE_URL: respect an existing value (e.g. from .env), else build a default.
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}}"

say() { printf '\n\033[1;36m==>\033[0m %s\n' "$1"; }

# --- 1. start Postgres (idempotent) ------------------------------------------
say "Starting PostgreSQL ${PG_VERSION}..."
if su postgres -c "${PG_BIN}/pg_ctl -D '${PG_DATA}' status" >/dev/null 2>&1; then
  echo "    already running."
else
  mkdir -p /var/run/postgresql
  chown postgres:postgres /var/run/postgresql
  su postgres -c "${PG_BIN}/pg_ctl -D '${PG_DATA}' -l '${PG_LOG}' start"
fi

# --- 2. wait until it accepts connections ------------------------------------
say "Waiting for Postgres to accept connections..."
for i in $(seq 1 30); do
  if su postgres -c "${PG_BIN}/pg_isready -h ${DB_HOST} -p ${DB_PORT}" >/dev/null 2>&1; then
    echo "    ready."
    break
  fi
  sleep 1
  if [ "$i" -eq 30 ]; then
    echo "    Postgres did not become ready. Check ${PG_LOG}." >&2
    exit 1
  fi
done

# --- 3. ensure role + database exist (idempotent) ----------------------------
say "Ensuring role '${DB_USER}' and database '${DB_NAME}' exist..."
su postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'\"" \
  | grep -q 1 \
  || su postgres -c "psql -c \"CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';\""

su postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'\"" \
  | grep -q 1 \
  || su postgres -c "psql -c \"CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};\""

# --- 4. migrate SQLite data the first time only ------------------------------
if [ -f instance/school.db ]; then
  say "Migrating SQLite data if target is empty (one-time)..."
  python scripts/sqlite_to_postgres.py --if-empty
else
  echo "    no instance/school.db to migrate from — skipping."
fi

# --- 5. launch the app -------------------------------------------------------
say "Launching PosyHub (DATABASE_URL -> ${DB_NAME} on ${DB_HOST}:${DB_PORT})"
exec python app.py
