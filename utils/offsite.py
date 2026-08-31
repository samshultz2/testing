"""
Offsite backup shipping (opt-in).

By default nothing is configured and ``ship()`` is a no-op — backups stay local.
Set one (or several) destinations in the environment and each finished backup
file is copied off the server automatically:

* ``OFFSITE_DIR``           — copy to a mounted path / external volume / NFS.
* ``OFFSITE_RCLONE_REMOTE`` — ``rclone copyto`` to any rclone remote (S3, B2,
                              Google Drive, SFTP…). Configure it once with
                              ``rclone config``; enable object-lock / versioning
                              on the bucket for WORM (ransomware-proof) backups.
* ``OFFSITE_COMMAND``       — escape hatch: an arbitrary command. The tokens
                              ``{path}`` and ``{name}`` are substituted (argv is
                              split first, then tokens replaced — no shell), e.g.
                              ``aws s3 cp {path} s3://my-bucket/edusyncra/{name}``.

Shipping is best-effort and never raises: a failed upload must not break the
backup run or app startup. Every attempt is logged.
"""
import os
import shlex
import shutil
import subprocess

# Generous ceiling for a single upload — large DB dumps over a slow link.
_TIMEOUT = 1800


def _cfg(app, key):
    return (app.config.get(key) or '').strip()


def is_configured(app):
    """True if at least one offsite destination is set."""
    return bool(_cfg(app, 'OFFSITE_DIR') or _cfg(app, 'OFFSITE_RCLONE_REMOTE')
                or _cfg(app, 'OFFSITE_COMMAND'))


def ship(app, path):
    """Copy a finished backup file to every configured offsite destination.

    No-op (returns False) when nothing is configured or the file is missing.
    Never raises — failures are logged and swallowed so the backup run survives.
    """
    if not path or not os.path.exists(path):
        return False
    if not is_configured(app):
        return False
    name = os.path.basename(path)
    shipped = False
    for fn in (_ship_dir, _ship_rclone, _ship_command):
        try:
            shipped = fn(app, path, name) or shipped
        except Exception as exc:
            app.logger.warning('offsite %s failed for %s: %s',
                               fn.__name__.lstrip('_'), name, exc)
    if shipped:
        app.logger.info('offsite: shipped %s', name)
    return shipped


def _ship_dir(app, path, name):
    dest_dir = _cfg(app, 'OFFSITE_DIR')
    if not dest_dir:
        return False
    os.makedirs(dest_dir, exist_ok=True)
    tmp = os.path.join(dest_dir, name + '.part')
    shutil.copy2(path, tmp)                 # write to a .part then rename: no torn file
    os.replace(tmp, os.path.join(dest_dir, name))
    return True


def _ship_rclone(app, path, name):
    remote = _cfg(app, 'OFFSITE_RCLONE_REMOTE')
    if not remote:
        return False
    flags = shlex.split(_cfg(app, 'OFFSITE_RCLONE_FLAGS'))
    target = remote.rstrip('/') + '/' + name
    proc = subprocess.run(['rclone', 'copyto', *flags, path, target],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=_TIMEOUT)
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout.decode('utf-8', 'replace')[-400:])
    return True


def _ship_command(app, path, name):
    tmpl = _cfg(app, 'OFFSITE_COMMAND')
    if not tmpl:
        return False
    # Split the template into argv first, then substitute tokens into each arg,
    # so a path with spaces stays a single argument and no shell is involved.
    argv = [a.replace('{path}', path).replace('{name}', name) for a in shlex.split(tmpl)]
    proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=_TIMEOUT)
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout.decode('utf-8', 'replace')[-400:])
    return True
