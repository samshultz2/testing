# Deploying EduSyncra on a Contabo VPS (direct nginx + TLS)

Tailored runbook for: **Contabo VPS ~4 vCPU / 8 GB / ~200 GB NVMe / Ubuntu**,
**direct nginx + Let's Encrypt**, **migrating your existing production data**, and
**Redis + PgBouncer included**. It builds on `deploy/setup_vps.sh` (which already
scripts Postgres, the app, secrets, and data restore) and adds the production edge
and scale tier the audit called for.

> You run these on the VPS over SSH; I can't reach the box. Paste me any error and
> I'll adjust. Times assume a fresh Ubuntu 22.04/24.04.

Capacity recap (see `docs/PRODUCTION_AUDIT.md`): this box is **PASS** for normal
use, 100–1,000 CBT, and the **~1,800 JAMB-Mock** target; **marginal** at 3,000 and
**needs a second app VPS** at 5,000. Nothing below blocks scaling later.

---

## Phase 0 — DNS (do first; propagation takes time)

Point your domain at the VPS's IPv4. Multi-tenant needs a **wildcard** so every
school subdomain resolves:

```
A     edusyncra.site        -> <VPS_IP>
A     *.edusyncra.site      -> <VPS_IP>
```

(Wildcard TLS needs a DNS-01 challenge — your DNS provider must have an API token
for certbot, or issue the wildcard cert manually. If you only serve the apex
school for now, a normal `-d edusyncra.site` cert is enough to start.)

## Phase 1 — Base server + firewall

```bash
sudo apt update && sudo apt -y upgrade
sudo adduser --disabled-password --gecos "" edusyncra   # run the app as a non-root user
sudo apt install -y ufw
sudo ufw allow OpenSSH
sudo ufw allow 80,443/tcp
sudo ufw enable
```

Redis (6379), PgBouncer (6432) and Postgres (5432) stay bound to `127.0.0.1` — the
firewall + loopback binding keep them off the internet. Never open them.

## Phase 2 — Get the code + run the base installer

```bash
sudo -iu edusyncra
git clone https://github.com/samshultz2/testing /opt/edusyncra   # or your remote
cd /opt/edusyncra
cp deploy/setup.env.example deploy/setup.env
nano deploy/setup.env      # set TENANT_BASE_DOMAIN, APEX_TENANT, DB_APP_PASSWORD,
                           # OWNER_* , SMTP_*, and OWNER_DB_DUMP (Phase 3), SETUP_TUNNEL=no
```

Don't run `setup_vps.sh` for a **populated multi-tenant** migration — it is built
for a fresh/owner-only install and would generate NEW secrets + create only the
owner+control DBs. For an existing multi-school install, use the `pg_dumpall` path
below (restores every school DB + the DB role) and write `.env` by hand from your
carried-over keys. `setup_vps.sh` remains the right tool for a fresh single-school
start.

## Phase 3 — Migrate your existing production data

### 3a. Single-school / fresh owner (simple case)

```bash
# on the current box:
bash deploy/migrate_db.sh export "postgresql://posyhub:PW@localhost:5432/posyhub" edusyncra_dump.sql
tar czf uploads.tar.gz uploads/
scp edusyncra_dump.sql uploads.tar.gz edusyncra@<VPS_IP>:/opt/edusyncra/
# on the VPS: set OWNER_DB_DUMP=/opt/edusyncra/edusyncra_dump.sql in deploy/setup.env,
tar xzf uploads.tar.gz && bash deploy/setup_vps.sh
```

### 3b. Multi-tenant (control plane + many school DBs) — RECOMMENDED for existing installs

Every school is its own database and each stored `tenants.database_url` embeds the
DB user+password, so the move must preserve the **role and its password** and
restore **all** databases. `pg_dumpall` does both in one file.

> **Carry over `FIELD_ENCRYPTION_KEY` unchanged.** Encrypted fields (portal
> passwords) are unreadable under a different key. Copy it (and `SECRET_KEY`, to
> avoid logging everyone out) from the old `.env` into the new one. Never let the
> new box generate fresh keys during a migration.

On the **current** box (read-only; leave the app running):

```bash
cd <app folder>
# keys + DB/tenancy settings to reuse verbatim on the VPS
grep -E 'FIELD_ENCRYPTION_KEY|SECRET_KEY|DATABASE_URL|CONTROL_PLANE_DATABASE_URL|TENANT_DATABASE_URL_TEMPLATE|MULTI_TENANT|TENANT_BASE_DOMAIN|APEX_TENANT|DB_' .env > ~/edusyncra_env_carryover.txt
chmod 600 ~/edusyncra_env_carryover.txt
# ALL databases + roles (control plane + every school) in one dump
sudo -u postgres pg_dumpall | gzip > ~/edusyncra_all.sql.gz
tar czf ~/edusyncra_uploads.tar.gz uploads/
# note your schools, to verify each after the move
sudo -u postgres psql -d edusyncra_control -c "SELECT subdomain, status FROM tenants ORDER BY subdomain;"
```

Copy to the VPS:

```bash
scp ~/edusyncra_all.sql.gz ~/edusyncra_uploads.tar.gz ~/edusyncra_env_carryover.txt edusyncra@<VPS_IP>:/opt/edusyncra/
```

On the **VPS** (Postgres installed, fresh cluster — do NOT pre-create the role/DBs):

```bash
cd /opt/edusyncra
# 1. restore every database + the app role (with its ORIGINAL password) in one shot
gunzip -c edusyncra_all.sql.gz | sudo -u postgres psql
# 2. restore media
tar xzf edusyncra_uploads.tar.gz
# 3. write .env by hand: paste the FIELD_ENCRYPTION_KEY/SECRET_KEY/DB_* /CONTROL_PLANE_*
#    /TENANT_* /MULTI_TENANT/TENANT_BASE_DOMAIN/APEX_TENANT lines from
#    edusyncra_env_carryover.txt, plus APP_ENV=production, TRUST_PROXY=1, FORCE_HTTPS=1.
#    Keep DB host/user/password identical so the stored tenant URLs still resolve.
nano .env
chmod 600 .env
```

Verify **before** going further — the control plane lists your schools and each
school DB has data:

```bash
sudo -u postgres psql -d edusyncra_control -c "SELECT subdomain, status FROM tenants ORDER BY subdomain;"
sudo -u postgres psql -d <a school's db name> -c "SELECT count(*) FROM students;"
```

> Introduce **PgBouncer + Redis (Phases 5–6) only AFTER data is restored and the
> site serves each school on :5432 directly.** Keeps the migration itself simple;
> the scale tier is then a deliberate switch, not part of the risky move.

## Phase 4 — PostgreSQL tuning for 8 GB

Edit `/etc/postgresql/*/main/postgresql.conf` (values for an 8 GB box shared with
the app + Redis):

```conf
max_connections = 200            # web workers × per-tenant pools; PgBouncer caps the real number
shared_buffers = 2GB
effective_cache_size = 5GB
work_mem = 16MB
maintenance_work_mem = 256MB
wal_compression = on
```

```bash
sudo systemctl restart postgresql
```

## Phase 5 — PgBouncer (connection pooling for many tenants)

```bash
sudo apt install -y pgbouncer
sudo cp deploy/pgbouncer.ini.example /etc/pgbouncer/pgbouncer.ini
sudo nano /etc/pgbouncer/pgbouncer.ini            # review pool sizes
# add the app role to the auth file (md5 of password+username):
HASH=$(printf 'md5%s' "$(echo -n 'PWposyhub' | md5sum | cut -d' ' -f1)")
echo "\"posyhub\" \"$HASH\"" | sudo tee /etc/pgbouncer/userlist.txt
sudo systemctl enable --now pgbouncer
```

Then point the app **through** PgBouncer and disable psycopg prepared statements
(edit `/opt/edusyncra/.env`):

```ini
PGBOUNCER=1
DATABASE_URL=postgresql+psycopg://posyhub:PW@127.0.0.1:6432/posyhub
TENANT_DATABASE_URL_TEMPLATE=postgresql+psycopg://posyhub:PW@127.0.0.1:6432/{name}
```

> If PgBouncer ever misbehaves, the safe fallback is to point the two URLs back at
> `:5432` (direct Postgres) and remove `PGBOUNCER=1`. With `max_connections=200`
> that alone carries the single-school 1,800 target.

## Phase 6 — Redis (cache + queue + async grading)

```bash
sudo apt install -y redis-server
# merge deploy/redis.conf.example into /etc/redis/redis.conf (bind 127.0.0.1,
# requirepass, maxmemory 512mb, allkeys-lru), then:
sudo systemctl enable --now redis-server
```

In `/opt/edusyncra/.env`:

```ini
REDIS_URL=redis://:YOUR_STRONG_PASSWORD@127.0.0.1:6379/0
CBT_ASYNC_GRADING=1          # queue grading so the deadline spike drains off the web tier
```

The app auto-detects Redis; without it, it falls back to an in-process cache and
inline grading (no error). Install the client lib into the venv:

```bash
/opt/edusyncra/.venv/bin/pip install "redis>=5"
```

## Phase 7 — systemd: web tier + background jobs (split)

`setup_vps.sh` may have installed the waitress/tunnel `edusyncra` unit — for this
direct-nginx path, use the gunicorn web unit + the dedicated jobs worker instead:

```bash
sudo systemctl disable --now edusyncra 2>/dev/null || true   # if it was installed
sudo cp deploy/edusyncra-web.service  /etc/systemd/system/
sudo cp deploy/edusyncra-jobs.service /etc/systemd/system/
# edit both: set User=edusyncra, WorkingDirectory=/opt/edusyncra, venv path
sudo systemctl daemon-reload
sudo systemctl enable --now edusyncra-web edusyncra-jobs
```

`edusyncra-web` runs gunicorn (4 workers × 4 threads) on `127.0.0.1:5000` with
`RUN_INPROCESS_JOBS=0`; `edusyncra-jobs` owns backups + the queue drain. Confirm:

```bash
sudo systemctl status edusyncra-web edusyncra-jobs
curl -s localhost:5000/healthz
```

## Phase 8 — nginx + TLS

```bash
sudo apt install -y nginx
sudo cp deploy/nginx-vps.conf /etc/nginx/sites-available/edusyncra
sudo nano /etc/nginx/sites-available/edusyncra     # set the /static/ alias to /opt/edusyncra/static/
sudo ln -sf /etc/nginx/sites-available/edusyncra /etc/nginx/sites-enabled/edusyncra
sudo rm -f /etc/nginx/sites-enabled/default

sudo apt install -y certbot python3-certbot-nginx
# apex + wildcard (wildcard needs DNS-01; follow the plugin for your DNS provider):
sudo certbot --nginx -d edusyncra.site
#   ...and for tenant subdomains, a wildcard via DNS-01, e.g.:
# sudo certbot certonly --dns-<provider> -d '*.edusyncra.site' -d edusyncra.site

sudo nginx -t && sudo systemctl reload nginx
```

Set the edge flags in `.env` (already defaulted by ProductionConfig, but be explicit):

```ini
APP_ENV=production
TRUST_PROXY=1
FORCE_HTTPS=1
```

`sudo systemctl restart edusyncra-web` after `.env` changes.

## Phase 9 — Backups + offsite

Daily encrypted DB + media backups already run in `edusyncra-jobs`. Turn on
**offsite** shipping (the single biggest DR win) in `.env` — pick one:

```ini
# OFFSITE_RCLONE_REMOTE=b2:my-bucket/edusyncra     # after `rclone config`
# OFFSITE_DIR=/mnt/backup-volume
# OFFSITE_COMMAND=aws s3 cp {path} s3://bkt/{name}
```

Test a restore into a scratch DB (non-destructive) from the in-app backup page, or:

```bash
/opt/edusyncra/.venv/bin/python -c "from app import app; from utils import backup; \
 app.app_context().push(); print(backup.verify_backup(app))"
```

## Phase 10 — Log rotation + disk safety

```bash
sudo tee /etc/logrotate.d/edusyncra >/dev/null <<'EOF'
/opt/edusyncra/instance/*.jsonl {
  weekly
  rotate 8
  compress
  missingok
  notifempty
  copytruncate
}
EOF
```

nginx/gunicorn logs go to journald (already rotated). Watch disk on `/platform`.

## Phase 11 — Verify + load-test BEFORE the first big exam

1. Browse `https://edusyncra.site` → your migrated school; sign in.
2. `https://edusyncra.site/platform` → CPU/RAM/PG connections/Redis all live.
3. Register a throwaway tenant on a subdomain; confirm it resolves + isolates.
4. **Load test on this box (or a staging clone)** with `loadtest/` before booking a
   real JAMB-Mock: `N=1800 python loadtest/seed_loadtest.py` then the Locust command
   in `loadtest/README.md`. Watch `/platform` at peak; capture
   `curl -s https://edusyncra.site/platform/health.json`.

---

## Rollback / safety

- **PgBouncer trouble** → point `DATABASE_URL`/`TENANT_DATABASE_URL_TEMPLATE` back
  at `:5432`, unset `PGBOUNCER`, `systemctl restart edusyncra-web`.
- **Redis trouble** → unset `REDIS_URL` (+ `CBT_ASYNC_GRADING`); the app falls back
  to in-process cache + inline grading with no data loss.
- **Bad deploy** → `git checkout <previous>` in `/opt/edusyncra`, restart the two
  units. Data is untouched (schema self-heals forward only).
- **Whole-VPS loss** → provision a new box, run Phases 1–8, restore the newest
  offsite DB dump + media tar via `setup.env`'s `OWNER_DB_DUMP`.

## Service map (what runs where)

| Component | Bind | Unit | Public? |
|---|---|---|---|
| nginx (TLS, static, gzip, rate-limit) | :80/:443 | `nginx` | **yes** |
| gunicorn web (4×4) | 127.0.0.1:5000 | `edusyncra-web` | no (via nginx) |
| background jobs + queue drain | — | `edusyncra-jobs` | no |
| PgBouncer | 127.0.0.1:6432 | `pgbouncer` | no |
| PostgreSQL | 127.0.0.1:5432 | `postgresql` | no |
| Redis | 127.0.0.1:6379 | `redis-server` | no |
