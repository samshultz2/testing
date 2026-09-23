"""Every fixed-brand page (admin shell, CBT/Mock JAMB portal, marketing site)
self-hosts its Google Fonts instead of fetching them from fonts.googleapis.com
— on a slow/unreliable connection an external-origin DNS+TLS round trip on
every page load is pure latency for something that never changes. The one
exception is the customer-facing Website Builder public site: each school
picks its own font at runtime (utils.site_themes.google_fonts_href), so that
page still loads from Google by design and must NOT be touched here."""
from config import Config
from tests.conftest import login_token


def test_admin_dashboard_self_hosts_fonts(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok},
           follow_redirects=True)
    html = c.get('/students').get_data(as_text=True)
    assert 'fonts.css' in html
    assert 'fonts.googleapis.com' not in html


def test_cbt_portal_login_self_hosts_fonts(app):
    c = app.test_client()
    html = c.get('/exam/login').get_data(as_text=True)
    assert 'fonts.css' in html
    assert 'fonts.googleapis.com' not in html


def test_marketing_home_self_hosts_fonts(app):
    c = app.test_client()
    html = c.get('/home').get_data(as_text=True)
    assert 'fonts.css' in html
    assert 'fonts.googleapis.com' not in html


def test_website_builder_public_site_still_uses_dynamic_google_font(app):
    """Unlike the fixed-brand pages above, a school's own public site picks
    its font at runtime and must keep loading from Google Fonts."""
    from utils.site_themes import google_fonts_href
    href = google_fonts_href({})
    assert href and 'fonts.googleapis.com' in href
