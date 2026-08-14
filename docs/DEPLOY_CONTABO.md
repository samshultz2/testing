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

Don't run `setup_vps.sh` yet if you're migrating data — set `OWNER_DB_DUMP` first
(Phase 3). It generates `SECRET_KEY` + `FIELD_ENCRYPTION_KEY`, creates the Postgres
role + databases, restores your dump, brings the schema to head, and writes `.env`.

## Phase 3 — Migrate your existing production data

On the **current** environment (where the app runs now), dump the live DB + media:

```bash
# database → a plain SQL dump
bash deploy/migrate_db.sh export "postgresql://posyhub:PW@localhost:5432/posyhub" edusyncra_dump.sql
# media (logos, question images, scans, comm attachments)
tar czf uploads.tar.gz uploads/
```

Copy both to the VPS:

```bash
scp edusyncra_dump.sql uploads.tar.gz edusyncra@<VPS_IP>:/opt/edusyncra/
```

On the VPS, point the installer at the dump and unpack media:

```bash
cd /opt/edusyncra
# in deploy/setup.env:  OWNER_DB_DUMP=/opt/edusyncra/edusyncra_dump.sql
tar xzf uploads.tar.gz        # restores uploads/
bash deploy/setup_vps.sh      # creates DBs, restores the dump, writes .env, schema→head
```

Verify the data landed before going further:

```bash
sudo -u postgres psql -d posyhub -c "SELECT count(*) FROM students;"
```

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
