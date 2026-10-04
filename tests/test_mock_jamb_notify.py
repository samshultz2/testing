"""Bulk-entering Mock JAMB results should alert the branch's admins so other
staff know an exam's results are ready, gated by the 'mock_results_entered'
automation toggle."""
import re
from datetime import date

from config import Config
from models import db, Student, AcademicSession, Notification, Branch, User
from models.mock_jamb import MockJAMBExam
from tests.conftest import login_token, enroll_sss3


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/students').get_data(as_text=True)).group(1)


def _add_default_branch_admin(username):
    bid = Branch.get_default().id
    u = User(username=username, full_name='Mock Exam Branch Admin', role='admin',
            branch_id=bid, password_hash='x', is_active=True)
    db.session.add(u); db.session.commit()
    return u.id, bid


_EXAM_NUMBER = [100]


def _build_exam_and_student(app, tag, bid):
    _EXAM_NUMBER[0] += 1
    with app.app_context():
        sess = AcademicSession.query.filter_by(is_active=True).first() or \
            AcademicSession(name=f'{tag}-Sess', is_active=True)
        db.session.add(sess); db.session.flush()
        exam = MockJAMBExam(name=f'ZzMock{tag}', exam_number=_EXAM_NUMBER[0], session_id=sess.id,
                            exam_date=date(2026, 2, 1), branch_id=bid)
        db.session.add(exam); db.session.flush()
        exam_id = exam.id
        s = Student(student_id=f'MJN{tag}', first_name='Mock', surname=f'Zz{tag}',
                   gender='Male', branch_id=bid, is_active=True)
        db.session.add(s); db.session.commit()
        student_id = s.id
    enroll_sss3(app, student_id)
    return exam_id, student_id


def test_bulk_entry_notifies_branch_admins(app):
    with app.app_context():
        admin_uid, bid = _add_default_branch_admin('zzmocknotify')
    exam_id, student_id = _build_exam_and_student(app, 'Notify', bid)
    c = _admin(app)
    tok = _csrf(c)
    r = c.post(f'/mock-jamb/exam/{exam_id}/results/bulk', data={
        f'score_{student_id}': '250', '_csrf_token': tok})
    assert r.status_code in (200, 302)
    with app.app_context():
        notes = Notification.query.filter_by(
            title='Mock exam results entered', user_id=admin_uid).all()
        assert notes, 'expected a bell notification after bulk-entering results'
        assert any('Mock JAMB' in (n.body or '') and '1 added' in (n.body or '')
                  for n in notes)


def test_disabling_mock_results_entered_automation_skips_notification(app):
    with app.app_context():
        from utils import automations
        automations.set_enabled('mock_results_entered', False)
        admin_uid, bid = _add_default_branch_admin('zzmocknotifyoff')
    exam_id, student_id = _build_exam_and_student(app, 'Off', bid)
    try:
        c = _admin(app)
        tok = _csrf(c)
        r = c.post(f'/mock-jamb/exam/{exam_id}/results/bulk', data={
            f'score_{student_id}': '260', '_csrf_token': tok})
        assert r.status_code in (200, 302)
        with app.app_context():
            notes = Notification.query.filter_by(user_id=admin_uid).all()
            assert not notes
    finally:
        with app.app_context():
            from utils import automations
            automations.set_enabled('mock_results_entered', True)
