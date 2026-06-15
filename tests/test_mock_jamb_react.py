"""Mock-JAMB converted pages (React shells) + JSON create."""
import re
from datetime import date

from config import Config
from models import db, AcademicSession
from models.mock_jamb import MockJAMBExam
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


def test_mock_jamb_shells(app):
    client = _admin(app)
    for url, page in {'/mock-jamb/': 'index', '/mock-jamb/exam/create': 'create_exam'}.items():
        html = client.get(url).get_data(as_text=True)
        assert 'mj-app' in html and 'mj-data' in html
        assert f'"page": "{page}"' in html


def test_create_exam_json(app):
    with app.app_context():
        s = AcademicSession.query.first() or AcademicSession(name='MJ-Sess', is_active=True)
        db.session.add(s); db.session.commit(); sid = s.id
    client = _admin(app)
    r = client.post('/mock-jamb/exam/create', headers={'X-Requested-With': 'fetch'},
                    data={'session_id': sid, 'exam_number': 2, 'exam_date': date.today().isoformat(),
                          '_csrf_token': _ptoken(client)})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        assert MockJAMBExam.query.filter_by(session_id=sid, exam_number=2).first() is not None
