"""Students Phase 2 — expanded search + new filters.

Search now matches parent name/phone/email, NIN and JAMB reg/profile in
addition to student name/ID; the list adds House and Boarding filters and
exposes the in-use house list.
"""
from config import Config
from models import db, Student, ParentContact, Branch
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD,
                           '_csrf_token': login_token(c)})
    return c


def _mk(app, **kw):
    with app.app_context():
        bid = Branch.get_default().id
        s = Student(branch_id=bid, is_active=True, gender=kw.pop('gender', 'Male'),
                    first_name=kw.pop('first_name', 'Q'), **kw)
        db.session.add(s); db.session.flush()
        sid = s.id
        db.session.commit()
        return sid


def test_search_by_parent_phone(app):
    c = _admin(app)
    with app.app_context():
        bid = Branch.get_default().id
        s = Student(student_id='ZZ_SRCH_PAR', first_name='Ada', surname='ZzSrchParent',
                    gender='Female', is_active=True, branch_id=bid)
        db.session.add(s); db.session.flush()
        db.session.add(ParentContact(student_id=s.id, phone_number='08099887766',
                                     name='Grace Parent', email='grace@example.com',
                                     is_primary=True))
        db.session.commit()
    j = c.get('/api/students?search=08099887766').get_json()
    ids = {x['student_id'] for x in j['students']}
    assert 'ZZ_SRCH_PAR' in ids
    # And by parent name.
    j = c.get('/api/students?search=Grace Parent').get_json()
    assert 'ZZ_SRCH_PAR' in {x['student_id'] for x in j['students']}


def test_search_by_nin_and_jamb(app):
    c = _admin(app)
    _mk(app, student_id='ZZ_SRCH_NIN', surname='ZzSrchNin', nin='55566677788',
        jamb_reg_number='2025JMB777')
    j = c.get('/api/students?search=55566677788').get_json()
    assert 'ZZ_SRCH_NIN' in {x['student_id'] for x in j['students']}
    j = c.get('/api/students?search=2025JMB777').get_json()
    assert 'ZZ_SRCH_NIN' in {x['student_id'] for x in j['students']}


def test_house_and_boarding_filter(app):
    c = _admin(app)
    _mk(app, student_id='ZZ_HOUSE_A', surname='ZzHouseA', house='Falcon',
        boarding_status='Boarding')
    _mk(app, student_id='ZZ_HOUSE_B', surname='ZzHouseB', house='Eagle',
        boarding_status='Day')
    j = c.get('/api/students?house=Falcon').get_json()
    sids = {x['student_id'] for x in j['students']}
    assert 'ZZ_HOUSE_A' in sids and 'ZZ_HOUSE_B' not in sids
    # In-use houses are surfaced in the filter options.
    assert 'Falcon' in j['filters']['houses'] and 'Eagle' in j['filters']['houses']
    # Boarding filter narrows too.
    j = c.get('/api/students?boarding=Day').get_json()
    sids = {x['student_id'] for x in j['students']}
    assert 'ZZ_HOUSE_B' in sids and 'ZZ_HOUSE_A' not in sids


def test_applied_echoes_new_filters(app):
    c = _admin(app)
    j = c.get('/api/students?house=Falcon&boarding=Boarding').get_json()
    assert j['applied']['house'] == 'Falcon'
    assert j['applied']['boarding'] == 'Boarding'
