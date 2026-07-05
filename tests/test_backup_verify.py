"""Restore-verification: prove a backup can actually be restored, non-destructively.

'A backup you haven't tested is not a backup.' verify_backup() restores the
newest backup somewhere disposable and sanity-checks it, without ever touching
the live database.
"""
import os


def test_verify_newest_backup_ok(app, tmp_path, monkeypatch):
    from utils import backup
    monkeypatch.setitem(app.config, 'BASE_DIR', str(tmp_path))  # backups -> temp, hermetic
    with app.app_context():
        made = backup.make_backup(app, label='verify_test')
        assert made and os.path.exists(made)
        ok, msg = backup.verify_backup(app)          # newest -> the one we just made
        assert ok is True, msg
        assert 'OK' in msg


def test_verify_reports_missing_backup(app, tmp_path, monkeypatch):
    from utils import backup
    empty = tmp_path / 'empty'
    empty.mkdir()
    monkeypatch.setitem(app.config, 'BASE_DIR', str(empty))
    with app.app_context():
        ok, msg = backup.verify_backup(app)
        assert ok is False
        assert 'no backup' in msg.lower()


def test_verify_detects_corrupt_backup(app, tmp_path, monkeypatch):
    """A truncated/garbage backup file must fail verification, not pass silently."""
    from utils import backup
    monkeypatch.setitem(app.config, 'BASE_DIR', str(tmp_path))
    bad = tmp_path / 'instance' / 'backups' / 'school_20260101.db'
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b'this is not a sqlite database')
    with app.app_context():
        ok, msg = backup.verify_backup(app, str(bad))
        assert ok is False, msg
