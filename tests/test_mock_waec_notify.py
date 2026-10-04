"""Saving Mock WAEC grid-entry scores should alert admins, same
'mock_results_entered' automation toggle as Mock JAMB's bulk entry."""
import uuid
from datetime import date

from config import Config
from models import db, Student, AcademicSession, Notification
from models.mock_waec import MockWAECExam
from tests.conftest import login_token, auth_csrf, enroll_sss3


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _session(app):
    with app.app_context():
        s = AcademicSession.query.filter_by(is_active=True).first() or \
            AcademicSession(name='2025/2026', is_active=True)
        db.session.add(s); db.session.commit()
        return s.id


def _exam(app, session_id, n):
    with app.app_context():
        ex = MockWAECExam(name=f'Mock {n}', exam_number=n, session_id=session_id,
                          exam_date=date(2025, 2, 1))
        db.session.add(ex); db.session.commit()
        return ex.id


def _student(app, adm, first, surname):
    with app.app_context():
        s = Student(student_id=adm, first_name=first, surname=surname, gender='Male')
        db.session.add(s); db.session.commit()
        return s.id


def test_grid_entry_save_notifies_admins(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=201)
    sid = _student(app, 'GRN' + uuid.uuid4().hex[:5].upper(), 'Notify', 'Zzgrid')
    enroll_sss3(app, sid)
    c = _admin(app)
    tok = auth_csrf(c)
    r = c.post(f'/mock-waec/exam/{exam_id}/grid', data={
        '_csrf_token': tok, 'action': 'save', 'col': ['Mathematics'],
        f'score_{sid}_mathematics': '75',
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        notes = Notification.query.filter_by(title='Mock exam results entered', role='admin').all()
        assert any('1 score(s) for 1 student(s)' in (n.body or '') for n in notes)


def test_disabling_mock_results_entered_skips_waec_notification(app):
    from utils import automations
    with app.app_context():
        automations.set_enabled('mock_results_entered', False)
        before = Notification.query.filter_by(title='Mock exam results entered', role='admin').count()
    try:
        ssid = _session(app)
        exam_id = _exam(app, ssid, n=202)
        sid = _student(app, 'GRO' + uuid.uuid4().hex[:5].upper(), 'Quiet', 'Zzgridoff')
        enroll_sss3(app, sid)
        c = _admin(app)
        tok = auth_csrf(c)
        c.post(f'/mock-waec/exam/{exam_id}/grid', data={
            '_csrf_token': tok, 'action': 'save', 'col': ['Mathematics'],
            f'score_{sid}_mathematics': '80',
        }, follow_redirects=True)
        with app.app_context():
            after = Notification.query.filter_by(title='Mock exam results entered', role='admin').count()
            assert after == before
    finally:
        with app.app_context():
            automations.set_enabled('mock_results_entered', True)
