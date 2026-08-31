#!/usr/bin/env bash
# Manual PostgreSQL backup -> instance/backups/school_<timestamp>_manual.sql
# Usage: bash scripts/backup_db.sh   (reads DATABASE_URL from env/.env)
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Load DATABASE_URL / BACKUP_ENCRYPTION_KEY from .env if not already set.
if [ -f .env ]; then
  [ -z "${DATABASE_URL:-}" ] && DATABASE_URL="$(grep -E '^DATABASE_URL=' .env | tail -1 | cut -d= -f2-)"
  [ -z "${BACKUP_ENCRYPTION_KEY:-}" ] && BACKUP_ENCRYPTION_KEY="$(grep -E '^BACKUP_ENCRYPTION_KEY=' .env | tail -1 | cut -d= -f2-)"
fi
: "${DATABASE_URL:?Set DATABASE_URL (or put it in .env)}"

# pg_dump wants a libpq URL: strip the SQLAlchemy +psycopg driver suffix.
LIBPQ_URL="$(printf '%s' "$DATABASE_URL" | sed -E 's#^postgresql\+[a-z0-9]+://#postgresql://#')"

mkdir -p instance/backups
STAMP="$(date +%Y%m%d_%H%M%S)"
if [ -n "${BACKUP_ENCRYPTION_KEY:-}" ]; then
  # AES-256 encrypted dump (.sql.enc). Decrypt at restore time with the same key.
  DEST="instance/backups/school_${STAMP}_manual.sql.enc"
  pg_dump --no-owner --no-privileges "$LIBPQ_URL" \
    | openssl enc -aes-256-cbc -pbkdf2 -salt -pass "pass:${BACKUP_ENCRYPTION_KEY}" -out "$DEST"
  echo "Encrypted backup written: $DEST ($(du -h "$DEST" | cut -f1))"
else
  DEST="instance/backups/school_${STAMP}_manual.sql"
  pg_dump --no-owner --no-privileges "$LIBPQ_URL" -f "$DEST"
  echo "Backup written: $DEST ($(du -h "$DEST" | cut -f1))"
fi
