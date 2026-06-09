#!/usr/bin/env bash
# Manual PostgreSQL backup -> instance/backups/school_<timestamp>_manual.sql
# Usage: bash scripts/backup_db.sh   (reads DATABASE_URL from env/.env)
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Load DATABASE_URL from .env if not already set.
if [ -z "${DATABASE_URL:-}" ] && [ -f .env ]; then
  DATABASE_URL="$(grep -E '^DATABASE_URL=' .env | tail -1 | cut -d= -f2-)"
fi
: "${DATABASE_URL:?Set DATABASE_URL (or put it in .env)}"

# pg_dump wants a libpq URL: strip the SQLAlchemy +psycopg driver suffix.
LIBPQ_URL="$(printf '%s' "$DATABASE_URL" | sed -E 's#^postgresql\+[a-z0-9]+://#postgresql://#')"

mkdir -p instance/backups
DEST="instance/backups/school_$(date +%Y%m%d_%H%M%S)_manual.sql"
pg_dump --no-owner --no-privileges "$LIBPQ_URL" -f "$DEST"
echo "Backup written: $DEST ($(du -h "$DEST" | cut -f1))"
