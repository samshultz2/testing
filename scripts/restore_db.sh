#!/usr/bin/env bash
# Restore a PostgreSQL backup produced by backup_db.sh / auto_backup.
# Usage: bash scripts/restore_db.sh instance/backups/school_XXXX.sql
# WARNING: this DROPs and recreates the target database. Stop the app first.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DUMP="${1:?Usage: bash scripts/restore_db.sh <dump.sql>}"
[ -f "$DUMP" ] || { echo "Dump not found: $DUMP" >&2; exit 1; }

if [ -f .env ]; then
  [ -z "${DATABASE_URL:-}" ] && DATABASE_URL="$(grep -E '^DATABASE_URL=' .env | tail -1 | cut -d= -f2-)"
  [ -z "${BACKUP_ENCRYPTION_KEY:-}" ] && BACKUP_ENCRYPTION_KEY="$(grep -E '^BACKUP_ENCRYPTION_KEY=' .env | tail -1 | cut -d= -f2-)"
fi
: "${DATABASE_URL:?Set DATABASE_URL (or put it in .env)}"

# Parse db name out of the URL (everything after the last '/').
DB_NAME="${DATABASE_URL##*/}"; DB_NAME="${DB_NAME%%\?*}"
DB_OWNER="${DB_USER:-posyhub}"

read -r -p "This will DROP and recreate database '$DB_NAME'. Type the db name to confirm: " CONFIRM
[ "$CONFIRM" = "$DB_NAME" ] || { echo "Aborted."; exit 1; }

su postgres -c "psql -c \"DROP DATABASE IF EXISTS ${DB_NAME};\""
su postgres -c "psql -c \"CREATE DATABASE ${DB_NAME} OWNER ${DB_OWNER};\""
LIBPQ_URL="$(printf '%s' "$DATABASE_URL" | sed -E 's#^postgresql\+[a-z0-9]+://#postgresql://#')"

# --single-transaction + ON_ERROR_STOP: the data load is atomic — a failure
# rolls the whole thing back rather than leaving a half-restored database.
case "$DUMP" in
  *.enc)
    : "${BACKUP_ENCRYPTION_KEY:?Encrypted dump needs BACKUP_ENCRYPTION_KEY}"
    openssl enc -d -aes-256-cbc -pbkdf2 -pass "pass:${BACKUP_ENCRYPTION_KEY}" -in "$DUMP" \
      | psql --single-transaction -v ON_ERROR_STOP=1 "$LIBPQ_URL" ;;
  *)
    psql --single-transaction -v ON_ERROR_STOP=1 "$LIBPQ_URL" -f "$DUMP" ;;
esac
echo "Restore complete from: $DUMP"
