"""Offsite backup shipping + media archive.

Offsite is opt-in and dormant by default; when a destination is configured, new
backups (DB dump + uploads/ media) are copied off the server. These tests use a
local OFFSITE_DIR / a shell-free command as the 'offsite' target.
"""
import os


def test_ship_is_noop_when_unconfigured(app, tmp_path):
    from utils import offsite
    src = tmp_path / 'school_x.sql'
    src.write_text('data')
    with app.app_context():
        assert offsite.is_configured(app) is False
        assert offsite.ship(app, str(src)) is False


def test_ship_to_offsite_dir(app, tmp_path, monkeypatch):
    from utils import offsite
    dest_dir = tmp_path / 'offsite'
    monkeypatch.setitem(app.config, 'OFFSITE_DIR', str(dest_dir))
    src = tmp_path / 'school_20260101.sql'
    src.write_text('the-dump')
    with app.app_context():
        assert offsite.is_configured(app) is True
        assert offsite.ship(app, str(src)) is True
        copied = dest_dir / 'school_20260101.sql'
        assert copied.exists() and copied.read_text() == 'the-dump'
        # No leftover temp file from the atomic write.
        assert not (dest_dir / 'school_20260101.sql.part').exists()


def test_ship_via_command_token_substitution(app, tmp_path, monkeypatch):
    from utils import offsite
    out = tmp_path / 'copied.sql'
    # A shell-free command: cp {path} <out>. Tokens are substituted per-arg.
    monkeypatch.setitem(app.config, 'OFFSITE_COMMAND', f'cp {{path}} {out}')
    src = tmp_path / 's.sql'
    src.write_text('via-cmd')
    with app.app_context():
        assert offsite.ship(app, str(src)) is True
        assert out.read_text() == 'via-cmd'


def test_ship_failure_is_swallowed(app, tmp_path, monkeypatch):
    """A broken offsite command must not raise — shipping is best-effort."""
    from utils import offsite
    monkeypatch.setitem(app.config, 'OFFSITE_COMMAND', 'false')  # exits non-zero
    src = tmp_path / 's.sql'
    src.write_text('x')
    with app.app_context():
        assert offsite.ship(app, str(src)) is False   # logged, not raised


def test_media_backup_creates_archive(app, tmp_path, monkeypatch):
    from utils import backup
    monkeypatch.setitem(app.config, 'BASE_DIR', str(tmp_path))   # backups -> temp, hermetic
    up = tmp_path / 'uploads'
    up.mkdir()
    (up / 'logo.png').write_bytes(b'PNGDATA')
    monkeypatch.setitem(app.config, 'UPLOAD_FOLDER', str(up))
    with app.app_context():
        path, created = backup._media_backup(app, '20260102')
        assert created is True
        assert path and path.endswith('.tar.gz') and os.path.exists(path)
        # Second call for the same stamp is a no-op (already taken).
        path2, created2 = backup._media_backup(app, '20260102')
        assert created2 is False and path2 == path


def test_media_backup_skipped_when_disabled(app, tmp_path, monkeypatch):
    from utils import backup
    monkeypatch.setitem(app.config, 'BASE_DIR', str(tmp_path))
    up = tmp_path / 'uploads'
    up.mkdir()
    (up / 'a.txt').write_text('x')
    monkeypatch.setitem(app.config, 'UPLOAD_FOLDER', str(up))
    monkeypatch.setitem(app.config, 'BACKUP_MEDIA', False)
    with app.app_context():
        path, created = backup._media_backup(app, '20260103')
        assert path is None and created is False


def test_make_backup_ships_offsite(app, tmp_path, monkeypatch):
    """An on-demand backup lands in the offsite destination too."""
    from utils import backup
    monkeypatch.setitem(app.config, 'BASE_DIR', str(tmp_path))
    dest_dir = tmp_path / 'offsite'
    monkeypatch.setitem(app.config, 'OFFSITE_DIR', str(dest_dir))
    with app.app_context():
        path = backup.make_backup(app, label='offsite_test')
        assert path and os.path.exists(path)
        assert os.path.basename(path) in os.listdir(dest_dir)
