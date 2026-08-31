#!/usr/bin/env python3
"""Create a database backup (backend-agnostic) and prune to BACKUP_RETENTION.

Works for both SQLite and PostgreSQL via utils.backup.auto_backup, which keeps
one backup per day and prunes old ones. Idempotent — safe to run from a cron job
or systemd timer as often as you like; it won't duplicate the day's backup.

    python scripts/backup.py

Backups are written to instance/backups/. Set BACKUP_ENCRYPTION_KEY to encrypt
PostgreSQL dumps (see scripts/backup_db.sh and docs/BACKUPS.md).
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app  # noqa: E402
from utils.backup import auto_backup, list_backups  # noqa: E402


def main():
    app = create_app()
    with app.app_context():
        path = auto_backup(app)
        if path:
            print(f'Backup OK: {os.path.basename(path)}')
            print('Stored backups:', ', '.join(b['name'] for b in list_backups(app)[:5]))
            return 0
        print('Backup did not run (no database file, or backup failed — check logs).',
              file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
