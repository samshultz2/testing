"""Students Phase 4 — new bulk operations: set house, set boarding status, and
draft a Communication message to selected students' parents.
"""
from config import Config
from models import db, Student, ParentContact, Branch
from models.models_comms import Message, MessageRecipient
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD,
                           '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return 'a' * 64


def _mk(app, **kw):
    with app.app_context():
        bid = Branch.get_default().id
        s = Student(branch_id=bid, is_active=True, gender=kw.pop('gender', 'Male'),
                    first_name=kw.pop('first_name', 'Q'), **kw)
        db.session.add(s); db.session.flush()
        sid = s.id
        db.session.commit()
        return sid


def test_bulk_set_house(app):
    c = _admin(app); token = _csrf(c)
    a = _mk(app, student_id='ZZ_BH_A', surname='ZzBhA')
    b = _mk(app, student_id='ZZ_BH_B', surname='ZzBhB')
    r = c.post('/students/bulk-house', data={'_csrf_token': token, 'house': 'Falcon',
                                             'student_ids': [a, b]},
               headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 200 and r.get_json()['updated'] == 2
    with app.app_context():
        assert db.session.get(Student, a).house == 'Falcon'
        assert db.session.get(Student, b).house == 'Falcon'


def test_bulk_set_boarding_validates(app):
    c = _admin(app); token = _csrf(c)
    a = _mk(app, student_id='ZZ_BB_A', surname='ZzBbA')
    # Bad value rejected.
    r = c.post('/students/bulk-boarding', data={'_csrf_token': token, 'boarding': 'Nope',
                                                'student_ids': [a]},
               headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 400
    # Valid value applied.
    r = c.post('/students/bulk-boarding', data={'_csrf_token': token, 'boarding': 'Boarding',
                                                'student_ids': [a]},
               headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 200
    with app.app_context():
        assert db.session.get(Student, a).boarding_status == 'Boarding'


def test_bulk_message_drafts_campaign(app):
    c = _admin(app); token = _csrf(c)
    with app.app_context():
        bid = Branch.get_default().id
        s = Student(student_id='ZZ_BM_A', first_name='Msg', surname='ZzBmA',
                    gender='Male', is_active=True, branch_id=bid)
        db.session.add(s); db.session.flush()
        db.session.add(ParentContact(student_id=s.id, phone_number='08055443322',
                                     name='Parent', is_primary=True))
        db.session.commit()
        sid = s.id
    r = c.post('/students/bulk-message',
               data={'_csrf_token': token, 'title': 'PTA', 'channel': 'SMS',
                     'body': 'Dear {parent}, meeting on Friday.', 'student_ids': [sid]},
               headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 200, r.get_data(as_text=True)
    j = r.get_json()
    assert j['ok'] and j['recipients'] >= 1 and j['review_url']
    with app.app_context():
        msg = db.session.get(Message, j['message_id'])
        assert msg is not None and msg.status == 'Draft'   # never auto-sent
        recs = MessageRecipient.query.filter_by(message_id=msg.id, student_id=sid).all()
        assert len(recs) == 1


def test_bulk_message_no_reachable_parent(app):
    c = _admin(app); token = _csrf(c)
    # Student with no parent contact -> nothing reachable.
    sid = _mk(app, student_id='ZZ_BM_NONE', surname='ZzBmNone')
    r = c.post('/students/bulk-message',
               data={'_csrf_token': token, 'channel': 'SMS',
                     'body': 'Hello {parent}.', 'student_ids': [sid]},
               headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 400
    assert 'reachable' in r.get_json()['error'].lower()
