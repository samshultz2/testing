"""Timetable pages converted to the React shell (JSON-aware)."""
import re

from config import Config
from tests.conftest import login_token


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def test_timetable_shells_render(app):
    client = _admin(app)
    for url, page in {
        '/timetable/': 'index',
        '/timetable/backups': 'backups',
    }.items():
        html = client.get(url).get_data(as_text=True)
        assert 'tt-app' in html and 'tt-data' in html, url
        assert f'"page": "{page}"' in html, url


def test_designer_stays_standalone(app):
    """The browser-only designer is intentionally left as its own page."""
    client = _admin(app)
    html = client.get('/timetable/designer').get_data(as_text=True)
    assert 'tt-app' not in html
