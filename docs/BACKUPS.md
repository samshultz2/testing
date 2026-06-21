# Backups & Restore

EduSyncra backs up its database automatically and keeps the recent history
pruned. This page covers what runs by default, how to schedule backups
independently of the app, encryption, and how to restore (and verify) a backup.

## What you get out of the box

- **Backend-aware.** SQLite databases are copied; PostgreSQL is dumped with
  `pg_dump --clean --if-exists`. See `utils/backup.py`.
- **One backup per day**, written to `instance/backups/` as
  `school_YYYYMMDD.{db,sql}`, pruned to `BACKUP_RETENTION` (default 10).
- **Runs automatically** in two places:
  - on app startup (`auto_backup` in `app.py`), and
  - daily from the jobs worker (in-process by default, or `scripts/run_jobs.py`
    when `RUN_INPROCESS_JOBS=0`).

This means a backup is taken whenever the app starts and once per day while it
runs. If the app is **never restarted and the worker isn't running**, schedule
backups explicitly — see below.

## Scheduling backups independently of the app

Pick **one** of these (don't double up for the same database):

### Option A — run the jobs worker (recommended for multi-worker deploys)
The worker already takes the daily backup (plus SMS dispatch and reminders):

```bash
sudo cp deploy/edusyncra-jobs.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now edusyncra-jobs
```
Start the web app with `RUN_INPROCESS_JOBS=0` so jobs fire exactly once.

### Option B — a dedicated systemd timer (backups only)
For setups that don't run the worker:

```bash
sudo cp deploy/edusyncra-backup.service deploy/edusyncra-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now edusyncra-backup.timer
systemctl list-timers edusyncra-backup.timer   # confirm next run
```

### Option C — cron
```cron
# Daily database backup at 02:00 (backend-agnostic, idempotent, self-pruning)
0 2 * * *  cd /opt/edusyncra && .venv/bin/python scripts/backup.py >> /var/log/edusyncra-backup.log 2>&1
```

All three call `auto_backup`, which is idempotent — running it repeatedly in a
day won't create duplicates.

## Encryption at rest

PostgreSQL dumps can be encrypted with AES-256-CBC by setting
`BACKUP_ENCRYPTION_KEY` (used by `scripts/backup_db.sh` and `scripts/restore_db.sh`).
Keep this key somewhere safe and separate from the backups — without it an
encrypted dump cannot be restored. Generate one with:

```bash
python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())"
```

## Restoring

- **From the UI:** Settings → Backup, upload the backup file. A pre-restore
  snapshot is taken automatically before anything is overwritten.
- **PostgreSQL (CLI):** `bash scripts/restore_db.sh instance/backups/school_XXXX.sql[.enc]`
- **SQLite (CLI):** stop the app and copy the chosen `school_YYYYMMDD.db` over
  `instance/school.db`, then start the app.

## Verify a backup (do this periodically)

A backup you haven't tested is not a backup. Quick checks:

```bash
# SQLite — confirm the file is a valid database with tables:
sqlite3 instance/backups/school_YYYYMMDD.db "SELECT count(*) FROM sqlite_master WHERE type='table';"

# PostgreSQL — restore into a scratch database and sanity-check:
createdb edusyncra_restore_test
psql edusyncra_restore_test < instance/backups/school_YYYYMMDD.sql
psql edusyncra_restore_test -c "SELECT count(*) FROM students;"
dropdb edusyncra_restore_test
```

A full restore drill (restore into a staging copy and log in) once a term is the
real test of your backup strategy.
