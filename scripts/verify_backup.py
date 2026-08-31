#!/usr/bin/env python3
"""Verify that a database backup can actually be restored.

A backup you have never restored is not a backup. This restores the newest
backup (or a named one) somewhere disposable and sanity-checks it, WITHOUT ever
touching the live database:

* SQLite   — decrypts (if needed), opens the file, runs PRAGMA integrity_check
             and confirms the schema loaded.
* Postgres — restores the dump into a throwaway scratch database, counts a core
             table, then drops the scratch database. Needs CREATEDB privilege
             and psql on PATH.

    python scripts/verify_backup.py                 # newest backup
    python scripts/verify_backup.py school_2026.sql # a specific file (name or path)

Exit code is 0 on success, 1 on failure — so a cron/systemd job can alert on it.
Schedule it weekly; see docs/BACKUPS.md.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app  # noqa: E402
from utils.backup import verify_backup, _backup_dir  # noqa: E402


def _resolve(app, arg):
    """Accept a bare filename (looked up in the backup dir) or a full path."""
    if not arg:
        return None
    if os.path.exists(arg):
        return arg
    return os.path.join(_backup_dir(app), arg)


def main():
    app = create_app()
    with app.app_context():
        path = _resolve(app, sys.argv[1] if len(sys.argv) > 1 else None)
        ok, msg = verify_backup(app, path)
        print(('VERIFY OK: ' if ok else 'VERIFY FAILED: ') + msg,
              file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
