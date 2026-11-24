"""Mock-JAMB converted pages (React shells) + JSON create."""
import re
from datetime import date

from config import Config
from models import db, AcademicSession, Student
from models.mock_jamb import MockJAMBExam, MockJAMBResult
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


def _exam_with_result(app):
    with app.app_context():
        sess = AcademicSession.query.first() or AcademicSession(name='MJR-Sess')
        if sess.id is None:
            db.session.add(sess); db.session.commit()
        # Unique per call so the module-scoped DB doesn't collide across tests.
        n = (MockJAMBExam.query.count() + 1) * 10
        ex = MockJAMBExam(name='React Exam', exam_number=n, session_id=sess.id, exam_date=date.today())
        db.session.add(ex); db.session.flush()
        st = Student(student_id=f'MJR{n}', first_name='R', surname='Eact', gender='Male', is_active=True)
        db.session.add(st); db.session.flush()
        db.session.add(MockJAMBResult(student_id=st.id, mock_exam_id=ex.id, total_score=280,
                                      subject1='English', subject1_score=70))
        db.session.commit()
        return ex.id, st.id, sess.id


def test_view_exam_progress_analytics_shells(app):
    exam_id, student_id, session_id = _exam_with_result(app)
    client = _admin(app)
    for url, page in {
        f'/mock-jamb/exam/{exam_id}': 'view_exam',
        f'/mock-jamb/student/{student_id}': 'student_progress',
        f'/mock-jamb/analytics?session_id={session_id}': 'analytics',
    }.items():
        html = client.get(url).get_data(as_text=True)
        assert 'mj-app' in html and 'mj-data' in html
        assert f'"page": "{page}"' in html


def test_view_exam_json_payload(app):
    exam_id, _student_id, _session_id = _exam_with_result(app)
    client = _admin(app)
    r = client.get(f'/mock-jamb/exam/{exam_id}', headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 200
    data = r.get_json()
    assert data['page'] == 'view_exam'
    assert data['results'] and data['results'][0]['rank'] == 1
    assert data['statistics']['statistics']['max'] == 280


def test_new_mock_gets_current_novel_existing_kept(app):
    with app.app_context():
        s = AcademicSession(name='2025/2026 NV', is_active=False); db.session.add(s); db.session.flush()
        old = MockJAMBExam(name='Old mock', exam_number=7, session_id=s.id, exam_date=date.today(),
                           novel_title='The Life Changer')
        db.session.add(old); db.session.commit(); sid, oid = s.id, old.id
    client = _admin(app)
    r = client.post('/mock-jamb/exam/create', headers={'X-Requested-With': 'fetch'},
                    data={'session_id': sid, 'exam_number': 8, 'exam_date': date.today().isoformat(),
                          '_csrf_token': _ptoken(client)})
    assert r.get_json()['ok']
    with app.app_context():
        new = MockJAMBExam.query.filter_by(session_id=sid, exam_number=8).first()
        assert new.novel_title == 'The Lekki Headmaster — Kabir Alabi Garba'      # UTME 2026
        assert db.session.get(MockJAMBExam, oid).novel_title == 'The Life Changer'   # untouched
    # re-saving the old mock's blueprint without changing the novel keeps it exactly
    page = client.get(f'/mock-jamb/exam/{oid}/blueprint').get_data(as_text=True)
    assert 'Saved for this mock' in page and 'value="The Life Changer" checked' in page
    client.post(f'/mock-jamb/exam/{oid}/blueprint',
                data={'_csrf_token': _ptoken(client), 'novel_title': 'The Life Changer'})
    with app.app_context():
        assert db.session.get(MockJAMBExam, oid).novel_title == 'The Life Changer'
