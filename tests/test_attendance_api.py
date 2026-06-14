"""Attendance JSON API (React offline pilot): roster read + idempotent mark write."""
import re
from datetime import date, timedelta

from config import Config
from models import (db, Branch, User, Student, ClassArmAssignment, SchoolClass,
                    ClassArm, Term, AcademicSession, StudentEnrollment, Week, Attendance)
from tests.conftest import login_token


def _setup(app):
    with app.app_context():
        term = Term.query.filter_by(is_active=True).first()
        if not term:
            sess = AcademicSession(name='AA-Sess', is_active=True)
            db.session.add(sess); db.session.flush()
            term = Term(session_id=sess.id, term_number=1, name='AA-Term', is_active=True)
            db.session.add(term); db.session.flush()
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        wk = Week.query.filter(Week.term_id == term.id,
                               Week.start_date <= today, Week.end_date >= today).first()
        if not wk:
            db.session.add(Week(term_id=term.id, week_number=99,
                                start_date=monday, end_date=monday + timedelta(days=6)))
        sc = SchoolClass.query.first(); arm = ClassArm.query.first()
        bid = Branch.get_default().id
        caa = ClassArmAssignment.query.filter_by(
            class_id=sc.id, arm_id=arm.id, term_id=term.id).first()
        if not caa:
            caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
            db.session.add(caa); db.session.flush()
        else:
            caa.branch_id = bid
        eids = []
        for nm in ('Ann', 'Bob'):
            sid = 'AA' + nm
            st = Student.query.filter_by(student_id=sid).first()
            if not st:
                st = Student(student_id=sid, first_name=nm, surname=nm,
                             gender='Male', is_active=True, branch_id=bid)
                db.session.add(st); db.session.flush()
            en = StudentEnrollment.query.filter_by(
                student_id=st.id, class_arm_assignment_id=caa.id).first()
            if not en:
                en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
                db.session.add(en); db.session.flush()
            eids.append(en.id)
        db.session.commit()
        return dict(caa=caa.id, eids=eids, date=today.isoformat(), bid=bid)


def _admin(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    return c, tok


def test_roster_returns_students_and_week(app):
    ids = _setup(app)
    c, _ = _admin(app)
    r = c.get(f'/attendance/api/roster?assignment_id={ids["caa"]}&date={ids["date"]}')
    assert r.status_code == 200
    j = r.get_json()
    assert j['week_id'] is not None
    names = {s['name'] for s in j['students']}
    assert {'Ann Ann', 'Bob Bob'} <= names
    assert all(s['morning_present'] for s in j['students'])   # default present


def test_mark_is_idempotent_upsert(app):
    ids = _setup(app)
    c, tok = _admin(app)
    body = {'assignment_id': ids['caa'], 'date': ids['date'],
            'session_type': 'morning', 'present': [ids['eids'][0]], 'auto_copy': True}
    for _ in range(2):                                       # twice -> same result
        m = c.post('/attendance/api/mark', json=body, headers={'X-CSRFToken': tok})
        assert m.status_code == 200 and m.get_json()['ok'] is True
    with app.app_context():
        present = Attendance.query.filter_by(enrollment_id=ids['eids'][0], date=date.today()).first()
        absent = Attendance.query.filter_by(enrollment_id=ids['eids'][1], date=date.today()).first()
        assert present.morning_present is True
        assert absent.morning_present is False


def test_mark_rejects_date_with_no_week(app):
    ids = _setup(app)
    c, tok = _admin(app)
    far = (date.today() + timedelta(days=400)).isoformat()   # outside any week
    m = c.post('/attendance/api/mark',
               json={'assignment_id': ids['caa'], 'date': far, 'present': []},
               headers={'X-CSRFToken': tok})
    assert m.status_code == 400


def test_cross_branch_is_forbidden(app):
    ids = _setup(app)
    with app.app_context():
        other = Branch(name='AA-Other', code='AAO', is_active=True)
        db.session.add(other); db.session.flush()
        u = User(username='aa_branchadmin', role='admin', scope='branch', branch_id=other.id)
        u.set_password('Secret123'); u.set_modules(['attendance'])
        db.session.add(u); db.session.commit()
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'username': 'aa_branchadmin', 'password': 'Secret123', '_csrf_token': tok})
    # roster + mark on a class in the DEFAULT branch -> 403 for the other-branch admin
    assert c.get(f'/attendance/api/roster?assignment_id={ids["caa"]}&date={ids["date"]}').status_code == 403
    m = c.post('/attendance/api/mark',
               json={'assignment_id': ids['caa'], 'date': ids['date'], 'present': []},
               headers={'X-CSRFToken': tok})
    assert m.status_code == 403
