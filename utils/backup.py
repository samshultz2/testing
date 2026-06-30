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


def _harden_perms(path, mode):
    """Best-effort chmod so backups/instance aren't world-readable. Never raises
    (no-op on filesystems/OSes that don't support POSIX modes)."""
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _backup_dir(app):
    d = os.path.join(app.config['BASE_DIR'], 'instance', 'backups')
    os.makedirs(d, exist_ok=True)
    # The instance dir holds the DB, backups and (in dev) the persisted secret
    # key — keep it owner-only, not the default world-readable 0755.
    _harden_perms(os.path.dirname(d), 0o700)
    _harden_perms(d, 0o700)
    return d


def _finalize(app, dest):
    """Encrypt a freshly-written backup at rest (when FIELD_ENCRYPTION_KEY is
    set) and lock it to owner-only. Returns dest, or None if it was dropped."""
    if not dest or not os.path.exists(dest):
        return None
    from utils import crypto
    try:
        if crypto.is_enabled():
            with open(dest, 'rb') as fh:
                raw = fh.read()
            if not crypto.bytes_look_encrypted(raw):
                with open(dest, 'wb') as fh:
                    fh.write(crypto.encrypt_bytes(raw))
        elif crypto._strict():
            # Strict mode but no key: a plaintext backup at rest is unacceptable.
            app.logger.error('REQUIRE_FIELD_ENCRYPTION is set but no key is '
                             'configured — refusing to keep a plaintext backup.')
            _safe_remove(dest)
            return None
    except Exception as exc:
        app.logger.warning('backup encryption failed for %s: %s', dest, exc)
    _harden_perms(dest, 0o600)
    return dest if os.path.exists(dest) else None


def _read_decrypted(upload_path):
    """Read a backup file, transparently decrypting it when it carries the
    encrypted-backup magic. Legacy plaintext backups pass through unchanged."""
    from utils import crypto
    with open(upload_path, 'rb') as fh:
        raw = fh.read()
    return crypto.decrypt_bytes(raw)


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
            return _finalize(app, _pg_dump(app, dest))
        db_path = _sqlite_path(app)
        if not db_path or not os.path.exists(db_path):
            return None
        dest = os.path.join(_backup_dir(app), f"school_{stamp}_{label}.db")
        shutil.copy2(db_path, dest)
        return _finalize(app, dest)
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
        # Decrypt the upload (if it's an encrypted backup) to a temp .sql that
        # psql can read; legacy plaintext dumps pass through unchanged.
        import tempfile
        sql_path = None
        try:
            data = _read_decrypted(upload_path)
        except Exception as exc:
            return False, f'Could not read backup (wrong encryption key?): {exc}'
        try:
            fd, sql_path = tempfile.mkstemp(suffix='.sql', dir=_backup_dir(app))
            with os.fdopen(fd, 'wb') as fh:
                fh.write(data)
            _harden_perms(sql_path, 0o600)
            proc = subprocess.run(
                # --single-transaction: the whole restore is one transaction, so
                # a mid-restore failure rolls back instead of leaving a
                # half-dropped/half-loaded database.
                ['psql', '--single-transaction', '-v', 'ON_ERROR_STOP=1',
                 '-f', sql_path, url],
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
        finally:
            if sql_path:
                _safe_remove(sql_path)

    # SQLite path: swap the file in.
    if not name.endswith('.db'):
        return False, 'On SQLite, please upload a .db backup file.'
    db_path = _sqlite_path(app)
    if not db_path:
        return False, 'Could not determine SQLite database path.'
    try:
        # Decrypt the upload (if encrypted) to the raw SQLite bytes; legacy
        # plaintext .db uploads pass straight through.
        try:
            data = _read_decrypted(upload_path)
        except Exception as exc:
            return False, f'Could not read backup (wrong encryption key?): {exc}'
        if os.path.exists(db_path):
            stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            snap = db_path.replace('.db', f'_pre_restore_{stamp}.db')
            shutil.copy2(db_path, snap)
            _finalize(app, snap)
        with open(db_path, 'wb') as fh:
            fh.write(data)
        _harden_perms(db_path, 0o600)
        _safe_remove(upload_path)
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
                _finalize(app, _pg_dump(app, dest))
            _prune(backup_dir, 'school_*.sql', retention)
            return dest if os.path.exists(dest) else None

        db_path = _sqlite_path(app)
        if not db_path or not os.path.exists(db_path):
            return None
        dest = os.path.join(backup_dir, f"school_{today}.db")
        if not os.path.exists(dest):
            shutil.copy2(db_path, dest)
            _finalize(app, dest)
        _prune(backup_dir, 'school_*.db', retention)
        return dest
    except Exception:
        # Backups must never block app startup.
        return None
