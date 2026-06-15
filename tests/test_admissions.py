"""Admissions (React shells + JSON actions + branch scoping)."""
import re

from config import Config
from models import db, Applicant
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


def test_admissions_pages_are_react_shells(app):
    client = _admin(app)
    pages = {'/admissions/': 'dashboard', '/admissions/applicants': 'applicants',
             '/admissions/applicants/add': 'applicant_form'}
    for url, page in pages.items():
        html = client.get(url).get_data(as_text=True)
        assert 'adm-app' in html and 'adm-data' in html
        assert f'"page": "{page}"' in html


def test_add_applicant_json(app):
    client = _admin(app)
    r = client.post('/admissions/applicants/add', headers={'X-Requested-With': 'fetch'},
                    data={'first_name': 'JSON', 'surname': 'Applicant', '_csrf_token': _ptoken(client)})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        a = Applicant.query.filter_by(first_name='JSON', surname='Applicant').first()
        assert a is not None
        html = client.get(f'/admissions/applicants/{a.id}').get_data(as_text=True)
        assert 'adm-app' in html and '"page": "applicant_detail"' in html
