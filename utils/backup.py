"""
Lightweight automatic database backups.

Supports both backends:

* **SQLite** — keep one timestamped copy of the database file per day under
  ``instance/backups`` (a fast file copy, no tooling required).
* **PostgreSQL** — keep one ``pg_dump`` (plain SQL) per day under the same
  folder. Requires ``pg_dump`` on PATH (provided by the postgresql client).

Both are pruned to the configured retention count and are safe to call on
every boot — backups must never block startup.
"""
import os
import glob
import shutil
import subprocess
from datetime import datetime


def _backup_dir(app):
    d = os.path.join(app.config['BASE_DIR'], 'instance', 'backups')
    os.makedirs(d, exist_ok=True)
    return d


def _uri(app):
    return app.config.get('SQLALCHEMY_DATABASE_URI', '') or ''


def _is_postgres(app):
    return _uri(app).startswith('postgresql')


def _libpq_url(uri):
    """Convert a SQLAlchemy Postgres URL to a libpq URL pg_dump understands."""
    # postgresql+psycopg://user:pass@host/db -> postgresql://user:pass@host/db
    scheme, _, rest = uri.partition('://')
    return scheme.split('+', 1)[0] + '://' + rest


def _pg_dump(app, dest):
    """Run pg_dump to ``dest``. Returns dest on success, else None.

    Dumps are self-restoring (``--clean --if-exists``): restoring one drops and
    recreates the objects, so it can be applied over an existing schema.
    """
    url = _libpq_url(_uri(app))
    try:
        with open(dest, 'wb') as fh:
            proc = subprocess.run(
                ['pg_dump', '--no-owner', '--no-privileges',
                 '--clean', '--if-exists', url],
                stdout=fh, stderr=subprocess.PIPE, timeout=300,
            )
        if proc.returncode != 0:
            app.logger.warning('pg_dump failed: %s',
                               proc.stderr.decode('utf-8', 'replace')[:500])
            _safe_remove(dest)
            return None
        return dest
    except FileNotFoundError:
        app.logger.warning('pg_dump not found on PATH; skipping Postgres backup.')
        return None
    except Exception as exc:
        app.logger.warning('Postgres backup error: %s', exc)
        _safe_remove(dest)
        return None


def _safe_remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _sqlite_path(app):
    uri = _uri(app)
    if not uri.startswith('sqlite:///'):
        return None
    return uri[len('sqlite:///'):]


def _prune(backup_dir, pattern, retention):
    existing = sorted(glob.glob(os.path.join(backup_dir, pattern)))
    for old in (existing[:-retention] if retention > 0 else []):
        _safe_remove(old)


def make_backup(app, label='manual'):
    """Create an on-demand timestamped backup. Returns the path, or None."""
    try:
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if _is_postgres(app):
            dest = os.path.join(_backup_dir(app), f"school_{stamp}_{label}.sql")
            return _pg_dump(app, dest)
        db_path = _sqlite_path(app)
        if not db_path or not os.path.exists(db_path):
            return None
        dest = os.path.join(_backup_dir(app), f"school_{stamp}_{label}.db")
        shutil.copy2(db_path, dest)
        return dest
    except Exception as exc:
        app.logger.warning('make_backup error: %s', exc)
        return None


def list_backups(app):
    """Stored backups, newest first: [{name, size, modified}]."""
    try:
        d = _backup_dir(app)
        out = []
        for pat in ('school_*.db', 'school_*.sql'):
            for p in glob.glob(os.path.join(d, pat)):
                st = os.stat(p)
                out.append({'name': os.path.basename(p), 'size': st.st_size,
                            'modified': datetime.fromtimestamp(st.st_mtime)})
        return sorted(out, key=lambda x: x['name'], reverse=True)
    except Exception:
        return []


def restore_database(app, upload_path, original_filename):
    """
    Restore the database from an uploaded backup. Backend-aware:

    * SQLite  — accepts a ``.db`` file and swaps it into place (app restart
      required afterwards).
    * Postgres — accepts a ``.sql`` dump (as produced here, with
      ``--clean --if-exists``) and applies it with ``psql``. A pre-restore
      backup is taken first.

    Returns (ok: bool, message: str).
    """
    name = (original_filename or '').lower()
    if _is_postgres(app):
        if not name.endswith('.sql'):
            return False, 'On PostgreSQL, please upload a .sql backup file.'
        # Safety snapshot before we overwrite anything.
        make_backup(app, label='pre_restore')
        url = _libpq_url(_uri(app))
        # Release pooled connections so DROP/CREATE in the dump aren't blocked.
        try:
            from models import db
            db.engine.dispose()
        except Exception:
            pass
        try:
            proc = subprocess.run(
                # --single-transaction: the whole restore is one transaction, so
                # a mid-restore failure rolls back instead of leaving a
                # half-dropped/half-loaded database.
                ['psql', '--single-transaction', '-v', 'ON_ERROR_STOP=1',
                 '-f', upload_path, url],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600,
            )
            if proc.returncode != 0:
                tail = proc.stdout.decode('utf-8', 'replace')[-800:]
                return False, f'Restore failed: {tail}'
            return True, 'Database restored from backup.'
        except FileNotFoundError:
            return False, 'psql not found on PATH; cannot restore on this host.'
        except Exception as exc:
            return False, f'Restore error: {exc}'

    # SQLite path: swap the file in.
    if not name.endswith('.db'):
        return False, 'On SQLite, please upload a .db backup file.'
    db_path = _sqlite_path(app)
    if not db_path:
        return False, 'Could not determine SQLite database path.'
    try:
        if os.path.exists(db_path):
            stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            shutil.copy2(db_path, db_path.replace('.db', f'_pre_restore_{stamp}.db'))
        shutil.move(upload_path, db_path)
        return True, 'Database restored. Please restart the application.'
    except Exception as exc:
        return False, f'Restore error: {exc}'


def auto_backup(app):
    """Keep one backup per day, pruned to BACKUP_RETENTION. Never raises."""
    try:
        backup_dir = _backup_dir(app)
        retention = int(app.config.get('BACKUP_RETENTION', 10))
        today = datetime.now().strftime('%Y%m%d')

        if _is_postgres(app):
            dest = os.path.join(backup_dir, f"school_{today}.sql")
            if not os.path.exists(dest):
                _pg_dump(app, dest)
            _prune(backup_dir, 'school_*.sql', retention)
            return dest if os.path.exists(dest) else None

        db_path = _sqlite_path(app)
        if not db_path or not os.path.exists(db_path):
            return None
        dest = os.path.join(backup_dir, f"school_{today}.db")
        if not os.path.exists(dest):
            shutil.copy2(db_path, dest)
        _prune(backup_dir, 'school_*.db', retention)
        return dest
    except Exception:
        # Backups must never block app startup.
        return None
