"""Term setup checklist page renders with step states."""
import re
from config import Config
from tests.conftest import login_token


def test_term_setup_renders(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    r = c.get('/academics/setup')
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'Term Setup' in body
    assert 'Students enrolled' in body and 'Weeks created' in body
