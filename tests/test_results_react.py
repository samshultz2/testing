"""Results management pages converted to the React shell (JSON-aware)."""
import re

from config import Config
from models import db, UniversityCutoff
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


def test_results_shells_render(app):
    client = _admin(app)
    for url, page in {
        '/results/': 'index',
        '/results/readiness': 'readiness',
        '/results/subject-enrolment': 'subject_enrolment',
        '/results/cutoffs': 'cutoffs',
    }.items():
        html = client.get(url).get_data(as_text=True)
        assert 'res-app' in html and 'res-data' in html, url
        assert f'"page": "{page}"' in html, url


def test_cutoff_save_json(app):
    client = _admin(app)
    r = client.post('/results/cutoffs/save', headers={'X-Requested-With': 'fetch'},
                    data={'university_name': 'Test Uni', 'course_name': 'Astronomy',
                          'min_credits': 6, 'jamb_cutoff': 230,
                          'required_subjects[]': ['Mathematics', 'Physics'],
                          '_csrf_token': _ptoken(client)}).get_json()
    assert r['ok']
    with app.app_context():
        c = UniversityCutoff.query.filter_by(university_name='Test Uni', course_name='Astronomy').first()
        assert c is not None and c.min_credits == 6 and c.jamb_cutoff == 230


def test_cutoff_save_requires_course(app):
    client = _admin(app)
    r = client.post('/results/cutoffs/save', headers={'X-Requested-With': 'fetch'},
                    data={'university_name': 'X', 'course_name': '  ', '_csrf_token': _ptoken(client)})
    assert r.status_code == 400 and 'Course name is required' in r.get_json()['error']


def test_subject_enrolment_detail_shell(app):
    client = _admin(app)
    html = client.get('/results/subject-enrolment/waec/Mathematics').get_data(as_text=True)
    assert '"page": "subject_enrolment_detail"' in html and '"exam": "waec"' in html
