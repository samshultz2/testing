# PosyHub on Termux — Production Runbook (nginx + gunicorn)

Quick, repeatable steps to run PosyHub in production on Termux + proot Ubuntu,
behind nginx. For the full explanation and the Linux-server stage, see
[`DEPLOYMENT.md`](DEPLOYMENT.md). For PostgreSQL setup/migration see
[`POSTGRES_TERMUX_PROOT.md`](POSTGRES_TERMUX_PROOT.md).

---

## One-time setup

### 1. `.env` (in the repo root)

```ini
APP_ENV=production
DATABASE_URL=postgresql+psycopg://posyhub:posyhub@localhost:5432/posyhub

# generate with: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=<paste a generated key>
ADMIN_PASSWORD=<a strong password>

# nginx fronts the app; gunicorn listens locally only
GUNICORN_BIND=127.0.0.1:5000
TRUST_PROXY=1

# plain HTTP over LAN for now
SESSION_COOKIE_SECURE=0
ENABLE_HSTS=0
```

### 2. Dependencies

```bash
pip install -r requirements.txt
```

### 3. Migrate data into Postgres (first time only)

```bash
python scripts/sqlite_to_postgres.py --force
```

### 4. nginx (inside proot)

```bash
apt install -y nginx
cp deploy/nginx-posyhub.conf /etc/nginx/sites-available/posyhub
ln -sf /etc/nginx/sites-available/posyhub /etc/nginx/sites-enabled/posyhub
rm -f /etc/nginx/sites-enabled/default
```

Edit `/etc/nginx/sites-available/posyhub` and set the `/static/` `alias` to your
repo path, e.g. `alias /root/storage_fix/shared/Download/hobby/testing/static/;`
(run `pwd` in the repo and append `/static/`). Then:

```bash
nginx -t && nginx
```

---

## Every time you want to run it

```bash
tmux new -s posyhub          # so it survives closing the terminal
bash scripts/start.sh        # starts Postgres, then gunicorn on 127.0.0.1:5000
# detach: Ctrl-b then d      |   reattach: tmux attach -t posyhub
```

If nginx isn't already running after a reboot:

```bash
nginx                        # start ; reload config later with: nginx -s reload
```

Reach it from any device on the same Wi-Fi at **`http://<phone-LAN-ip>/`**
(find the IP with `ip addr`). Note: port 80, no `:5000` — nginx is the front door.

---

## Verify it's healthy

```bash
curl -s http://127.0.0.1/healthz      # -> {"status":"ok"}
```

Watch the gunicorn log (in the tmux pane) for `PRODUCTION:` warnings — with
`SECRET_KEY`, `ADMIN_PASSWORD`, `APP_ENV=production` and Postgres set, there
should be none.

---

## Stop / restart

```bash
# stop the app: reattach to tmux and press Ctrl-C, or:
tmux kill-session -t posyhub

# stop nginx
nginx -s stop

# stop Postgres
su postgres -c "/usr/lib/postgresql/16/bin/pg_ctl -D /var/lib/postgresql/16/main stop"
```

---

## Backups

* Automatic: one `pg_dump` per day under `instance/backups` (pruned to
  `BACKUP_RETENTION`).
* Manual: `bash scripts/backup_db.sh`
* Restore (app stopped): `bash scripts/restore_db.sh instance/backups/school_XXXX.sql`
  — or upload the `.sql` on the **Settings → Backup** page.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `nginx: bind() to 0.0.0.0:80 failed` | change `listen 80;` to `listen 8080;` in the config; use `http://<ip>:8080/` |
| `PRODUCTION: SECRET_KEY is not set` | the var isn't being read — confirm it's in `.env` with no quotes/space issues |
| App can't reach DB | start Postgres: `bash scripts/start.sh` (it does this), or check `pg_lsclusters` |
| Port 5000 already in use | a stale gunicorn is running — `pkill gunicorn` then restart |
| `502 Bad Gateway` from nginx | gunicorn isn't up, or `GUNICORN_BIND` ≠ what nginx proxies to (127.0.0.1:5000) |
