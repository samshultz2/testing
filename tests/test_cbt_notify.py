"""Creating or publishing a CBT exam should alert the branch's admins --
staff-facing only, since a student's CBT portal session only exists while
they're actively on the exam-taking page (no persistent identity this app
could notify into). Gated by the 'cbt_exam_scheduled' automation toggle."""
import re

from config import Config
from models import db, Branch, CBTExam, Notification, Subject, SchoolClass, User
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


def _add_default_branch_admin(username):
    """notify_branch_admins() addresses real admin User rows individually, not
    a role broadcast, so one must exist scoped to the default branch (what
    branch_for_new() resolves to for the legacy admin login used here) for a
    notification to land -- same requirement as the HR/generator tests."""
    bid = Branch.get_default().id
    u = User(username=username, full_name='CBT Branch Admin', role='admin',
            branch_id=bid, password_hash='x', is_active=True)
    db.session.add(u); db.session.commit()
    return u.id


def test_creating_exam_notifies_branch_admins(app):
    with app.app_context():
        admin_uid = _add_default_branch_admin('zzcbtnotifycreate')
    client = _admin(app)
    tok = _ptoken(client)
    r = client.post('/cbt/exams/add', headers={'X-Requested-With': 'fetch'},
                    data={'title': 'ZzCBT Notify Exam', 'access_password': 'go123',
                          'exam_date': '2026-06-20', 'duration_minutes': 20,
                          '_csrf_token': tok}).get_json()
    assert r['ok']
    with app.app_context():
        e = CBTExam.query.filter_by(title='ZzCBT Notify Exam').first()
        assert e is not None
        notes = Notification.query.filter_by(title='CBT exam scheduled', user_id=admin_uid).all()
        assert notes, 'expected a bell notification when the exam was created'
        assert any('ZzCBT Notify Exam' in (n.body or '') for n in notes)


def test_publishing_exam_notifies_branch_admins(app):
    with app.app_context():
        admin_uid = _add_default_branch_admin('zzcbtnotifypub')
    client = _admin(app)
    tok = _ptoken(client)
    r = client.post('/cbt/exams/add', headers={'X-Requested-With': 'fetch'},
                    data={'title': 'ZzCBT Publish Exam', 'access_password': 'go123',
                          'exam_date': '2026-06-21', 'duration_minutes': 20,
                          '_csrf_token': tok}).get_json()
    assert r['ok']
    with app.app_context():
        e = CBTExam.query.filter_by(title='ZzCBT Publish Exam').first()
        eid = e.id
        from models import CBTQuestion
        db.session.add(CBTQuestion(exam_id=eid, question_text='1+1?',
                                   option_a='1', option_b='2', correct_option='B', marks=1))
        db.session.commit()

    tok2 = _ptoken(client)
    r2 = client.post(f'/cbt/exams/{eid}/publish', data={'_csrf_token': tok2},
                     headers={'X-Requested-With': 'fetch'}, follow_redirects=True)
    assert r2.status_code == 200
    with app.app_context():
        e = CBTExam.query.get(eid)
        assert e.is_published is True
        notes = Notification.query.filter_by(title='CBT exam published', user_id=admin_uid).all()
        assert notes, 'expected a bell notification when the exam was published'
        assert any('ZzCBT Publish Exam' in (n.body or '') for n in notes)


def test_disabling_cbt_exam_scheduled_automation_skips_notification(app):
    with app.app_context():
        from utils import automations
        automations.set_enabled('cbt_exam_scheduled', False)
        admin_uid = _add_default_branch_admin('zzcbtnotifyoff')
    try:
        client = _admin(app)
        tok = _ptoken(client)
        r = client.post('/cbt/exams/add', headers={'X-Requested-With': 'fetch'},
                        data={'title': 'ZzCBT Quiet Exam', 'access_password': 'go123',
                              'exam_date': '2026-06-22', 'duration_minutes': 20,
                              '_csrf_token': tok}).get_json()
        assert r['ok']
        with app.app_context():
            notes = Notification.query.filter_by(user_id=admin_uid).all()
            assert not notes
    finally:
        with app.app_context():
            from utils import automations
            automations.set_enabled('cbt_exam_scheduled', True)
