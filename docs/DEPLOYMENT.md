# Deploying PosyHub in Production

PosyHub runs as a standard Flask app behind a WSGI server (gunicorn). This
guide covers two stages:

1. **Termux / proot (now)** — production on an Android device over LAN.
2. **Linux server (later)** — a VPS/box behind nginx with HTTPS.

Both use the same app and `DATABASE_URL`; only the process manager and the
front proxy differ.

---

## Prerequisites (both stages)

* PostgreSQL running and a database created — see
  [`POSTGRES_TERMUX_PROOT.md`](POSTGRES_TERMUX_PROOT.md).
* Data migrated from SQLite (one time):
  `python scripts/sqlite_to_postgres.py` (see that doc).
* Dependencies installed: `pip install -r requirements.txt` (includes
  `gunicorn` and `psycopg`).

## Configuration (`.env`)

Copy `.env.example` to `.env` and set at minimum:

```ini
APP_ENV=production
SECRET_KEY=<output of: python -c "import secrets; print(secrets.token_hex(32))">
ADMIN_PASSWORD=<a strong password>          # or ENABLE_LEGACY_LOGIN=0
DATABASE_URL=postgresql+psycopg://posyhub:posyhub@localhost:5432/posyhub
```

On startup the app logs a `PRODUCTION:` warning for anything still insecure
(unset `SECRET_KEY`, default admin password, SQLite). Aim for zero warnings.

`GET /healthz` returns `{"status":"ok"}` (200) when the app and database are
healthy — use it for uptime checks and proxy health probes.

---

## Stage 1 — Termux / proot (production over LAN)

The one-command launcher runs everything (start Postgres → wait → ensure DB →
migrate once → launch). It defaults to **production/gunicorn**:

```bash
bash scripts/start.sh
```

To run it by hand:

```bash
export APP_ENV=production
export DATABASE_URL="postgresql+psycopg://posyhub:posyhub@localhost:5432/posyhub"
gunicorn -c gunicorn.conf.py wsgi:app
```

Then reach it from another device on the same Wi-Fi at
`http://<phone-LAN-ip>:5000`.

**Keep it running** after you close the terminal — use `tmux` (or `nohup`):

```bash
pkg install tmux        # if needed
tmux new -s posyhub
bash scripts/start.sh
# detach with Ctrl-b then d ; reattach with: tmux attach -t posyhub
```

**Concurrency note:** the app runs an in-process background thread (scheduled
messages + daily backup). Keep `WEB_CONCURRENCY=1` (the default) and scale with
threads (`GUNICORN_THREADS`). Running multiple worker *processes* would start
duplicate background threads — only do that after moving those jobs to a
separate process.

**Backups** run automatically (one `pg_dump` per day under `instance/backups`,
pruned to `BACKUP_RETENTION`). Manual: `bash scripts/backup_db.sh`. Restore via
script: `bash scripts/restore_db.sh instance/backups/school_XXXX.sql`, or from
the **Settings → Backup** page (upload the `.sql` dump — it is applied with
`psql`; a pre-restore snapshot is taken automatically). To schedule backups
independently of the app (systemd timer or cron) and to verify a backup, see
[docs/BACKUPS.md](BACKUPS.md).

### Optional: nginx on Termux/proot

You do **not** have to wait for a Linux server to put nginx in front — it runs
in proot too, and is worth it for serving static files and (later) TLS:

A ready-to-use config lives at
[`deploy/nginx-posyhub.conf`](../deploy/nginx-posyhub.conf):

```bash
apt install -y nginx
cp deploy/nginx-posyhub.conf /etc/nginx/sites-available/posyhub
ln -sf /etc/nginx/sites-available/posyhub /etc/nginx/sites-enabled/posyhub
rm -f /etc/nginx/sites-enabled/default
# edit the /static/ alias path in the config to your repo location, then:
nginx -t && nginx          # reload later with: nginx -s reload
```

In `.env` set:

```ini
GUNICORN_BIND=127.0.0.1:5000   # gunicorn local-only; nginx is public-facing
TRUST_PROXY=1                  # honour X-Forwarded-* from nginx
```

`start.sh` loads `.env`, so gunicorn picks these up automatically. There's no
systemd in proot, so run nginx (it daemonizes) and gunicorn under `tmux`. Reach
it from another LAN device at `http://<phone-LAN-ip>/` (port 80). HTTPS via
certbot needs a public domain, so on a LAN you'd stay on plain HTTP until you
move to a server with a domain name.

---

## Stage 2 — Linux server behind nginx + HTTPS

### 1. App service (systemd)

`/etc/systemd/system/posyhub.service`:

```ini
[Unit]
Description=PosyHub
After=network.target postgresql.service
Wants=postgresql.service

[Service]
User=posyhub
WorkingDirectory=/opt/posyhub
EnvironmentFile=/opt/posyhub/.env
ExecStart=/opt/posyhub/venv/bin/gunicorn -c gunicorn.conf.py wsgi:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Set in `.env` for this stage:

```ini
APP_ENV=production
TRUST_PROXY=1
SESSION_COOKIE_SECURE=1
ENABLE_HSTS=1
GUNICORN_BIND=127.0.0.1:5000
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now posyhub
sudo systemctl status posyhub
```

### 2. nginx reverse proxy

```nginx
server {
    listen 80;
    server_name posyhub.example.com;

    client_max_body_size 16m;   # matches MAX_CONTENT_LENGTH

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

`TRUST_PROXY=1` makes the app honour `X-Forwarded-For/-Proto` (correct client
IPs and HTTPS detection for secure cookies + HSTS).

### 3. HTTPS

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d posyhub.example.com
```

Once TLS is live, `SESSION_COOKIE_SECURE=1` and `ENABLE_HSTS=1` take effect.

### 4. Scaling beyond one process

The web app runs scheduled messages + daily backup in an in-process thread,
which is correct for a single worker. To run multiple workers, move those jobs
to one separate process:

```ini
# .env
WEB_CONCURRENCY=4
RUN_INPROCESS_JOBS=0
```

Run the web app and the jobs worker side by side:

```bash
gunicorn -c gunicorn.conf.py wsgi:app     # web, 4 workers
python scripts/run_jobs.py                # jobs, exactly one process
```

As a systemd unit (`posyhub-jobs.service`), mirror `posyhub.service` but with
`ExecStart=.../python scripts/run_jobs.py`. The worker forces
`RUN_INPROCESS_JOBS=0` itself, so the jobs fire exactly once regardless of how
many web workers are running.

---

## Checklist

- [ ] `APP_ENV=production`, no `PRODUCTION:` warnings in the logs
- [ ] Strong `SECRET_KEY` and `ADMIN_PASSWORD` (or legacy login disabled)
- [ ] `DATABASE_URL` points at PostgreSQL; data migrated
- [ ] `/healthz` returns 200
- [ ] Daily backups appearing under `instance/backups`
- [ ] (Linux) behind nginx, HTTPS on, `TRUST_PROXY=1`, secure cookies + HSTS
