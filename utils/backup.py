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


def _media_backup(app, stamp):
    """Archive the uploads/ media folder (logos, question images, scans) — it is
    NOT part of the database dump, so without this it is never backed up.

    Written into the same backup dir as ``media_<stamp>.tar.gz``, encrypted and
    hardened like the DB backup. Returns ``(path, created)``; ``created`` is True
    only when a new archive was written this call (so callers ship it once)."""
    try:
        if not app.config.get('BACKUP_MEDIA', True):
            return None, False
        src = app.config.get('UPLOAD_FOLDER')
        if not src or not os.path.isdir(src) or not any(os.scandir(src)):
            return None, False        # nothing to archive yet
        dest = os.path.join(_backup_dir(app), f'media_{stamp}.tar.gz')
        if os.path.exists(dest):
            return dest, False        # already taken for this stamp
        import tarfile
        tmp = dest + '.tmp'
        with tarfile.open(tmp, 'w:gz') as tar:
            tar.add(src, arcname='uploads')
        os.replace(tmp, dest)
        final = _finalize(app, dest)
        return final, bool(final)
    except Exception as exc:
        app.logger.warning('media backup error: %s', exc)
        return None, False


def make_backup(app, label='manual'):
    """Create an on-demand timestamped backup. Returns the path, or None.
    The finished file is shipped offsite when a destination is configured."""
    try:
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if _is_postgres(app):
            dest = os.path.join(_backup_dir(app), f"school_{stamp}_{label}.sql")
            final = _finalize(app, _pg_dump(app, dest))
        else:
            db_path = _sqlite_path(app)
            if not db_path or not os.path.exists(db_path):
                return None
            dest = os.path.join(_backup_dir(app), f"school_{stamp}_{label}.db")
            shutil.copy2(db_path, dest)
            final = _finalize(app, dest)
        if final:
            from utils import offsite
            offsite.ship(app, final)
        return final
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


def _newest_backup(app):
    """Path to the most recent DB backup for this backend, or None."""
    d = _backup_dir(app)
    pattern = 'school_*.sql' if _is_postgres(app) else 'school_*.db'
    files = sorted(glob.glob(os.path.join(d, pattern)))
    return files[-1] if files else None


def _safe_count(conn, table):
    try:
        return conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
    except Exception:
        return '?'


def _verify_sqlite(app, path):
    import sqlite3
    import tempfile
    data = _read_decrypted(path)          # transparently decrypts encrypted backups
    fd, tmp = tempfile.mkstemp(suffix='.db', dir=_backup_dir(app))
    try:
        with os.fdopen(fd, 'wb') as fh:
            fh.write(data)
        _harden_perms(tmp, 0o600)
        conn = sqlite3.connect(tmp)
        try:
            integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
            if integrity != 'ok':
                return False, f'integrity check failed: {integrity}'
            ntables = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            if not ntables:
                return False, 'restored database has no tables'
            return True, f'OK — opened cleanly, {ntables} tables, ' \
                         f'{_safe_count(conn, "students")} students'
        finally:
            conn.close()
    finally:
        _safe_remove(tmp)


def _verify_postgres(app, path):
    """Restore the dump into a throwaway scratch database and count a table.

    Non-destructive: the live database is never touched. Needs CREATEDB
    privilege and psql on PATH — returns a clear message when it can't.
    """
    from urllib.parse import urlsplit, urlunsplit
    u = urlsplit(_libpq_url(_uri(app)))
    src_db = u.path.lstrip('/') or 'postgres'
    scratch = f'{src_db}_verify_{datetime.now().strftime("%Y%m%d%H%M%S")}'
    admin_url = urlunsplit((u.scheme, u.netloc, '/postgres', '', ''))
    scratch_url = urlunsplit((u.scheme, u.netloc, '/' + scratch, '', ''))

    def _psql(url, *args, sql=None):
        cmd = ['psql', url, '-v', 'ON_ERROR_STOP=1', *args]
        if sql is not None:
            cmd += ['-c', sql]
        return subprocess.run(cmd, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=600)

    import tempfile
    fd, sqlf = tempfile.mkstemp(suffix='.sql', dir=_backup_dir(app))
    created = False
    try:
        try:
            with os.fdopen(fd, 'wb') as fh:
                fh.write(_read_decrypted(path))
        except Exception as exc:
            return False, f'could not read backup (wrong encryption key?): {exc}'
        _harden_perms(sqlf, 0o600)
        # Create the scratch DB.
        r = _psql(admin_url, sql=f'CREATE DATABASE "{scratch}" TEMPLATE template0')
        if r.returncode != 0:
            return False, ('could not create scratch database (needs CREATEDB '
                           'privilege): ' + r.stdout.decode('utf-8', 'replace')[-300:])
        created = True
        # Restore into it, all-or-nothing.
        r = _psql(scratch_url, '--single-transaction', '-f', sqlf)
        if r.returncode != 0:
            return False, 'restore into scratch DB failed: ' + \
                          r.stdout.decode('utf-8', 'replace')[-400:]
        # Sanity-count a core table.
        r = _psql(scratch_url, '-tA', sql='SELECT count(*) FROM students')
        count = r.stdout.decode('utf-8', 'replace').strip() if r.returncode == 0 else '?'
        return True, f'OK — restored into a scratch database, {count} students'
    except FileNotFoundError:
        return False, 'psql not found on PATH; cannot verify on this host.'
    except subprocess.TimeoutExpired:
        return False, 'verification timed out.'
    finally:
        _safe_remove(sqlf)
        if created:
            # Drop the scratch DB (best-effort; FORCE closes any stray sessions).
            try:
                _psql(admin_url, sql=f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')
            except Exception:
                try:
                    _psql(admin_url, sql=f'DROP DATABASE IF EXISTS "{scratch}"')
                except Exception:
                    app.logger.warning('could not drop scratch DB %s — drop it manually',
                                       scratch)


def verify_backup(app, path=None):
    """Prove a backup actually restores — 'a backup you haven't tested is not a
    backup'. Defaults to the newest backup. Non-destructive: the live database
    is never modified. Returns ``(ok: bool, message: str)`` and never raises."""
    try:
        path = path or _newest_backup(app)
        if not path or not os.path.exists(path):
            return False, 'no backup found to verify.'
        name = os.path.basename(path)
        ok, msg = (_verify_postgres if _is_postgres(app) else _verify_sqlite)(app, path)
        return ok, f'{name}: {msg}'
    except Exception as exc:
        return False, f'verification error: {exc}'


def auto_backup(app):
    """Keep one DB + media backup per day, pruned to BACKUP_RETENTION, and ship
    newly-created backups offsite when a destination is configured. Never raises."""
    try:
        backup_dir = _backup_dir(app)
        retention = int(app.config.get('BACKUP_RETENTION', 10))
        today = datetime.now().strftime('%Y%m%d')

        dest = None
        created = False
        if _is_postgres(app):
            dest = os.path.join(backup_dir, f"school_{today}.sql")
            if not os.path.exists(dest):
                dest = _finalize(app, _pg_dump(app, dest))
                created = bool(dest)
            _prune(backup_dir, 'school_*.sql', retention)
        else:
            db_path = _sqlite_path(app)
            if db_path and os.path.exists(db_path):
                dest = os.path.join(backup_dir, f"school_{today}.db")
                if not os.path.exists(dest):
                    shutil.copy2(db_path, dest)
                    dest = _finalize(app, dest)
                    created = bool(dest)
                _prune(backup_dir, 'school_*.db', retention)

        # Media (uploads/) — separate archive, not covered by the DB dump.
        media, media_created = _media_backup(app, today)
        _prune(backup_dir, 'media_*.tar.gz', retention)

        # Ship only what we created this run (no-op unless offsite is configured),
        # so a restart doesn't re-upload the same day's backup.
        from utils import offsite
        if created:
            offsite.ship(app, dest)
        if media_created:
            offsite.ship(app, media)
        return dest
    except Exception:
        # Backups must never block app startup.
        return None
