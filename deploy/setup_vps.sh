#!/usr/bin/env bash
# EduSyncra — one-shot multi-tenant setup for a fresh VPS.
#
#   cp deploy/setup.env.example deploy/setup.env   # then fill it in
#   bash deploy/setup_vps.sh
#
# Idempotent: creates the Postgres role + databases, a Python venv, a complete
# .env (generating SECRET_KEY / FIELD_ENCRYPTION_KEY once), brings your owner
# school's database to the current schema, registers it as the free-forever
# apex school, and installs the daily billing cron. Re-running never drops data
# or rotates your secrets.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)
CONF="${1:-$HERE/setup.env}"
log() { printf '\n\033[1;32m▸ %s\033[0m\n' "$*"; }

[ -f "$CONF" ] || { echo "config not found: $CONF"; echo "  cp $HERE/setup.env.example $HERE/setup.env  then edit it"; exit 1; }
set -a; . "$CONF"; set +a

: "${TENANT_BASE_DOMAIN:?set TENANT_BASE_DOMAIN in setup.env}"
: "${APEX_TENANT:?set APEX_TENANT in setup.env}"
: "${DB_APP_USER:?}"; : "${DB_APP_PASSWORD:?}"; : "${DB_OWNER_NAME:?}"; : "${DB_CONTROL_NAME:?}"
PG_HOST="${PG_HOST:-localhost}"; PG_PORT="${PG_PORT:-5432}"

# 1. system packages (Debian/Ubuntu) — only if missing
if command -v apt-get >/dev/null 2>&1; then
  if ! command -v psql >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
    log "installing system packages (postgres, python)"
    sudo apt-get update -y
    sudo apt-get install -y python3 python3-venv python3-pip postgresql postgresql-client libpq-dev
    sudo systemctl enable --now postgresql || true
  fi
fi

PSQL_SUPER() { sudo -u postgres psql -v ON_ERROR_STOP=1 -qtA "$@"; }

# 2. Postgres role (app == provisioner, with CREATEDB) + databases
log "postgres role + databases"
PSQL_SUPER <<SQL
DO \$do\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='${DB_APP_USER}') THEN
    CREATE ROLE ${DB_APP_USER} LOGIN PASSWORD '${DB_APP_PASSWORD}' CREATEDB;
  ELSE
    ALTER ROLE ${DB_APP_USER} WITH LOGIN PASSWORD '${DB_APP_PASSWORD}' CREATEDB;
  END IF;
END \$do\$;
SQL
for db in "$DB_OWNER_NAME" "$DB_CONTROL_NAME"; do
  if [ "$(PSQL_SUPER -c "SELECT 1 FROM pg_database WHERE datname='${db}'")" != "1" ]; then
    PSQL_SUPER -c "CREATE DATABASE \"${db}\" OWNER ${DB_APP_USER}"
    echo "  created database ${db}"
  else
    echo "  database ${db} already exists — kept"
  fi
done

DBURL="postgresql+psycopg://${DB_APP_USER}:${DB_APP_PASSWORD}@${PG_HOST}:${PG_PORT}"

# 3. restore your current database (optional)
if [ -n "${OWNER_DB_DUMP:-}" ]; then
  log "restoring your current database from ${OWNER_DB_DUMP}"
  bash "$HERE/migrate_db.sh" import "$OWNER_DB_DUMP" "${DBURL}/${DB_OWNER_NAME}"
fi

# 4. Python venv + dependencies
log "python venv + dependencies"
cd "$ROOT"
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

# 5. write .env (keep existing secrets if present)
log "writing .env"
keep() { [ -f .env ] && awk -F= -v k="$1" '$1==k{sub(/^[^=]*=/,"");print;exit}' .env || true; }
SECRET_KEY=$(keep SECRET_KEY);            [ -n "$SECRET_KEY" ]            || SECRET_KEY=$(python -c 'import secrets;print(secrets.token_urlsafe(48))')
FIELD_ENCRYPTION_KEY=$(keep FIELD_ENCRYPTION_KEY); [ -n "$FIELD_ENCRYPTION_KEY" ] || FIELD_ENCRYPTION_KEY=$(python -c 'import os,base64;print(base64.b64encode(os.urandom(32)).decode())')
umask 077
cat > .env <<ENV
APP_ENV=production
SECRET_KEY=${SECRET_KEY}
FIELD_ENCRYPTION_KEY=${FIELD_ENCRYPTION_KEY}

MULTI_TENANT=1
TENANT_BASE_DOMAIN=${TENANT_BASE_DOMAIN}
APEX_TENANT=${APEX_TENANT}

DATABASE_URL=${DBURL}/${DB_OWNER_NAME}
CONTROL_PLANE_DATABASE_URL=${DBURL}/${DB_CONTROL_NAME}
PROVISIONER_DATABASE_URL=${DBURL}/postgres
TENANT_DATABASE_URL_TEMPLATE=${DBURL}/{name}

TENANT_PRICE_KOBO=${TENANT_PRICE_KOBO:-0}
TENANT_TERM_DAYS=${TENANT_TERM_DAYS:-120}
PLATFORM_PAYSTACK_SECRET_KEY=${PLATFORM_PAYSTACK_SECRET_KEY:-}
PLATFORM_PAYSTACK_PUBLIC_KEY=${PLATFORM_PAYSTACK_PUBLIC_KEY:-}

SMTP_HOST=${SMTP_HOST:-}
SMTP_PORT=${SMTP_PORT:-587}
SMTP_USER=${SMTP_USER:-}
SMTP_PASSWORD=${SMTP_PASSWORD:-}
SMTP_FROM=${SMTP_FROM:-}
ENV
echo "  wrote $ROOT/.env (chmod 600)"

# 6. owner school: schema to head, seed if empty, register as apex owner
log "initialising the owner school"
python scripts/init_owner.py \
  --subdomain "${APEX_TENANT}" --name "${OWNER_SCHOOL_NAME:-My School}" \
  --email "${OWNER_ADMIN_EMAIL:-}" --db-url "${DBURL}/${DB_OWNER_NAME}"

# 7. daily billing cron (reminders + purge)
log "installing daily billing cron (07:15)"
mkdir -p "$ROOT/logs"
JOB="15 7 * * * cd $ROOT && $ROOT/.venv/bin/python scripts/billing_cron.py >> $ROOT/logs/billing.log 2>&1"
if command -v crontab >/dev/null 2>&1; then
  ( crontab -l 2>/dev/null | grep -v 'scripts/billing_cron.py' ; echo "$JOB" ) | crontab -
  echo "  cron installed"
else
  echo "  crontab not found — add this line to your scheduler:"; echo "    $JOB"
fi

log "SETUP COMPLETE"
cat <<DONE

Start the app (production):
    cd $ROOT && .venv/bin/python app_production.py     # waitress on :5000

Then, in Cloudflare (DNS only):
  • wildcard  *.${TENANT_BASE_DOMAIN}  and the apex  ->  your tunnel
  • Paystack webhook URL:  https://api.${TENANT_BASE_DOMAIN}/billing/webhook

Your existing school is live at  https://${TENANT_BASE_DOMAIN}
New schools register at          https://signup.${TENANT_BASE_DOMAIN}/register
Super-admin console:             https://${TENANT_BASE_DOMAIN}/platform
DONE
