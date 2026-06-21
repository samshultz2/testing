"""Verifies the mobile header fix is actually rendered: the hamburger and the
branch switcher coexist in the header, and the CSS that stops the switcher from
covering the hamburger on small screens is present in the served page."""
from config import Config
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_mobile_header_fix_is_served(app):
    c = _admin(app)
    html = c.get('/').get_data(as_text=True)        # dashboard extends base.html
    # Both header controls are present...
    assert 'mobile-menu-btn' in html and 'fa-bars' in html      # the hamburger
    assert 'branch-switch' in html                              # the switcher
    # ...and the fix that keeps the switcher from covering the hamburger on
    # narrow screens is in the page (right cluster shrinks + name truncates).
    assert 'max-width: 40vw' in html
    assert 'text-overflow: ellipsis' in html
