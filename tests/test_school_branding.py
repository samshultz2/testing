"""School branding: the one school-wide logo upload + the shared school_profile
helper that feeds the shell header and every printout."""
import io
import os

from config import Config
from tests.conftest import login_token, auth_csrf


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _png_bytes(w=400, h=300, colour=(10, 120, 90)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (w, h), colour).save(buf, 'PNG')
    buf.seek(0)
    return buf


def test_school_profile_logo_none_when_unset(app):
    """No logo uploaded → logo_path None, logo_url '' (printouts fall back)."""
    from utils.school import school_profile, logo_path
    with app.app_context():
        # ensure clean
        from models import db, SchoolSettings
        s = SchoolSettings.query.filter_by(key='school_logo_url').first()
        if s:
            db.session.delete(s); db.session.commit()
        p = logo_path()
        if p and os.path.exists(p):
            os.remove(p)
        prof = school_profile()
        assert prof['logo_path'] is None
        assert prof['logo_url'] == ''


def test_upload_resizes_and_sets_logo_then_remove(app):
    """Posting a tall PNG saves a resized PNG and records school_logo_url; the
    remove endpoint clears both."""
    from models import db, SchoolSettings
    from utils.school import logo_path, logo_flowable
    c = _admin(app)
    tok = auth_csrf(c)

    r = c.post('/settings/school/logo',
               data={'_csrf_token': tok, 'school_logo': (_png_bytes(600, 600), 'logo.png')},
               content_type='multipart/form-data', follow_redirects=False)
    assert r.status_code in (200, 302, 303)

    with app.app_context():
        url = SchoolSettings.get('school_logo_url', '')
        assert url and 'uploads/branding/logo.png' in url
        p = logo_path()
        assert p and os.path.exists(p)
        from PIL import Image
        with Image.open(p) as im:
            assert im.height <= 240            # resized down from 600
        assert logo_flowable() is not None      # reportlab flowable builds

    # Remove → setting gone, file gone, profile falls back
    r = c.post('/settings/school/logo/remove', data={'_csrf_token': tok},
               follow_redirects=False)
    assert r.status_code in (200, 302, 303)
    with app.app_context():
        assert not SchoolSettings.get('school_logo_url', '')
        assert logo_path() is None


def test_upload_rejects_non_image(app):
    c = _admin(app)
    tok = auth_csrf(c)
    r = c.post('/settings/school/logo',
               data={'_csrf_token': tok, 'school_logo': (io.BytesIO(b'not an image'), 'evil.txt')},
               content_type='multipart/form-data', follow_redirects=True)
    # rejected by extension allow-list — no logo recorded
    from models import SchoolSettings
    with app.app_context():
        assert not SchoolSettings.get('school_logo_url', '')


def test_shell_shows_logged_in_user_not_hardcoded_admin(app):
    """Regression for the 'always shows Admin' bug: the shell renders the actual
    session user. The legacy admin logs in as 'Admin', so the name must come from
    session['user'] (the old code read the wrong key and always showed Admin)."""
    c = _admin(app)
    html = c.get('/students').get_data(as_text=True)
    # brand-sub carries "user · role" for the signed-in person
    assert 'brand-sub' in html
    assert 'Administrator' in html        # role label from school_brand
