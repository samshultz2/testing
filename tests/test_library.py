"""Library section (React shells + JSON actions)."""
import re

from config import Config
from models import db, Book
from tests.conftest import login_token


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def _ptoken(client):
    html = client.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def test_library_pages_are_react_shells(app):
    client = _admin(app)
    pages = {'/library/': 'dashboard', '/library/books': 'books',
             '/library/books/add': 'book_form', '/library/issue': 'issue',
             '/library/loans': 'loans', '/library/settings': 'settings'}
    for url, page in pages.items():
        html = client.get(url).get_data(as_text=True)
        assert 'library-app' in html and 'library-data' in html
        assert f'"page": "{page}"' in html


def test_add_book_json(app):
    client = _admin(app)
    r = client.post('/library/books/add', headers={'X-Requested-With': 'fetch'},
                    data={'title': 'JSON Atlas', 'copies_total': '3', '_csrf_token': _ptoken(client)})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        b = Book.query.filter_by(title='JSON Atlas').first()
        assert b is not None and b.copies_total == 3 and b.copies_available == 3
