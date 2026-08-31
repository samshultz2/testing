"""Promotion section React shells."""
from config import Config
from tests.conftest import login_token


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def test_promotion_pages_are_react_shells(app):
    client = _admin(app)
    pages = {'/promotion/': 'index', '/promotion/rules': 'rules', '/promotion/rules/add': 'add_rule',
             '/promotion/process': 'process', '/promotion/graduates': 'graduates',
             '/promotion/history': 'history'}
    for url, page in pages.items():
        html = client.get(url).get_data(as_text=True)
        assert 'promo-app' in html and 'promo-data' in html
        assert f'"page": "{page}"' in html
