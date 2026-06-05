"""
Lightweight automatic database backups.

On startup we keep one timestamped copy of the SQLite database per day under
``instance/backups`` and prune to the configured retention count. This needs no
scheduler and is safe to call on every boot.
"""
import os
import glob
import shutil
from datetime import datetime


def auto_backup(app):
    try:
        uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if not uri.startswith('sqlite:///'):
            return None
        db_path = uri[len('sqlite:///'):]
        if not os.path.exists(db_path):
            return None

        backup_dir = os.path.join(app.config['BASE_DIR'], 'instance', 'backups')
        os.makedirs(backup_dir, exist_ok=True)

        dest = os.path.join(backup_dir, f"school_{datetime.now():%Y%m%d}.db")
        if not os.path.exists(dest):
            shutil.copy2(db_path, dest)

        retention = int(app.config.get('BACKUP_RETENTION', 10))
        existing = sorted(glob.glob(os.path.join(backup_dir, 'school_*.db')))
        for old in existing[:-retention] if retention > 0 else []:
            try:
                os.remove(old)
            except OSError:
                pass
        return dest
    except Exception:
        # Backups must never block app startup.
        return None
