#!/usr/bin/env bash
# Move your current school database to the VPS — painlessly.
#
#   On your CURRENT machine (phone/Termux), dump it:
#       bash deploy/migrate_db.sh export "postgresql://posyhub:posyhub@localhost:5432/posyhub" edusyncra_dump.sql
#
#   Copy the file over:
#       scp edusyncra_dump.sql user@your-vps:~/
#
#   On the VPS, either point OWNER_DB_DUMP at it in setup.env (setup does the
#   import for you), or import manually:
#       bash deploy/migrate_db.sh import edusyncra_dump.sql \
#            "postgresql://posyhub:PASSWORD@localhost:5432/posyhub"
#
# The dump is portable: it carries all your data AND the alembic_version, so the
# restored database comes up at the right schema revision.
set -euo pipefail

# pg_dump/psql want plain postgresql://, not the app's postgresql+psycopg://
strip() { printf '%s' "${1/+psycopg/}"; }

cmd="${1:-}"
case "$cmd" in
  export)
    SRC="${2:-${DATABASE_URL:-}}"
    OUT="${3:-edusyncra_dump.sql}"
    [ -n "$SRC" ] || { echo "usage: $0 export <SOURCE_DB_URL> [out.sql]"; exit 1; }
    echo "▸ dumping -> $OUT"
    pg_dump --no-owner --no-privileges --clean --if-exists -d "$(strip "$SRC")" -f "$OUT"
    echo "✓ wrote $OUT ($(du -h "$OUT" | cut -f1)). Copy it to the VPS with scp."
    ;;
  import)
    DUMP="${2:-}"; DEST="${3:-}"
    { [ -n "$DUMP" ] && [ -n "$DEST" ]; } || { echo "usage: $0 import <dump.sql> <DEST_DB_URL>"; exit 1; }
    [ -f "$DUMP" ] || { echo "no such dump file: $DUMP"; exit 1; }
    echo "▸ restoring $DUMP -> ${DEST%%\?*}"
    psql -v ON_ERROR_STOP=1 -d "$(strip "$DEST")" -f "$DUMP"
    echo "✓ restore complete."
    ;;
  *)
    echo "usage: $0 export <SOURCE_DB_URL> [out.sql]"
    echo "       $0 import <dump.sql> <DEST_DB_URL>"
    exit 1;;
esac
