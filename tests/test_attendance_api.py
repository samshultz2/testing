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
            wk = Week(term_id=term.id, week_number=99,
                      start_date=monday, end_date=monday + timedelta(days=6))
            db.session.add(wk); db.session.flush()
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
        return dict(caa=caa.id, eids=eids, date=today.isoformat(), bid=bid, week=wk.id)


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


def test_context_lists_term_classes_weeks(app):
    _setup(app)
    c, _ = _admin(app)
    j = c.get('/attendance/api/context').get_json()
    assert j['term'] is not None
    assert any(k in j for k in ('classes', 'weeks', 'terms'))
    assert isinstance(j['weeks'], list) and isinstance(j['classes'], list)


def test_week_grid_roundtrip(app):
    ids = _setup(app)
    c, tok = _admin(app)
    g = c.get(f'/attendance/api/week?assignment_id={ids["caa"]}&week_id={ids["week"]}')
    assert g.status_code == 200
    gj = g.get_json()
    assert gj['week_id'] == ids['week'] and gj['days'] and gj['students']
    day = gj['days'][0]['date']
    # mark Ann absent (am/pm false) on the first school day
    m = c.post('/attendance/api/week/mark', headers={'X-CSRFToken': tok}, json={
        'assignment_id': ids['caa'], 'week_id': ids['week'],
        'marks': [{'enrollment_id': ids['eids'][0], 'date': day, 'am': False, 'pm': False}],
    })
    assert m.status_code == 200 and m.get_json()['ok'] is True
    g2 = c.get(f'/attendance/api/week?assignment_id={ids["caa"]}&week_id={ids["week"]}').get_json()
    ann = next(s for s in g2['students'] if s['enrollment_id'] == ids['eids'][0])
    assert ann['days'][day] == {'am': False, 'pm': False}


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


def test_daily_summary_report(app):
    ids = _setup(app)
    c, _ = _admin(app)
    r = c.get(f'/attendance/api/daily-summary?assignment_id={ids["caa"]}&date={ids["date"]}')
    assert r.status_code == 200
    j = r.get_json()
    assert j['date'] == ids['date'] and 'class_name' in j
    assert len(j['students']) >= 2


def test_weekly_report(app):
    ids = _setup(app)
    c, _ = _admin(app)
    r = c.get(f'/attendance/api/report/weekly?assignment_id={ids["caa"]}&week_id={ids["week"]}')
    assert r.status_code == 200
    j = r.get_json()
    assert j['week_info']['week_id'] == ids['week']
    assert isinstance(j['school_days'], list) and 'class_totals' in j


def test_termly_report_serialises_weeks(app):
    ids = _setup(app)
    c, _ = _admin(app)
    r = c.get(f'/attendance/api/report/termly?assignment_id={ids["caa"]}')
    assert r.status_code == 200
    j = r.get_json()
    # weeks must be JSON-friendly dicts, not Week objects
    assert all(set(w) == {'id', 'number'} for w in j['weeks'])
    assert 'termly_percentage' in j['class_totals']


def test_alerts_report_scoped(app):
    ids = _setup(app)
    c, _ = _admin(app)
    r = c.get('/attendance/api/report/alerts?threshold=100')
    assert r.status_code == 200
    j = r.get_json()
    assert j['threshold'] == 100.0 and isinstance(j['alerts'], list)
    # with a 100% threshold and no marks, both setup students should be flagged
    assert any(a['student_name'] in ('Ann Ann', 'Bob Bob') for a in j['alerts'])


def test_report_cross_branch_is_forbidden(app):
    ids = _setup(app)
    with app.app_context():
        other = Branch.query.filter_by(code='AAO').first()
        if not other:
            other = Branch(name='AA-Other', code='AAO', is_active=True)
            db.session.add(other); db.session.flush()
        u = User.query.filter_by(username='aa_reportadmin').first()
        if not u:
            u = User(username='aa_reportadmin', role='admin', scope='branch', branch_id=other.id)
            u.set_password('Secret123'); u.set_modules(['attendance'])
            db.session.add(u); db.session.commit()
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'username': 'aa_reportadmin', 'password': 'Secret123', '_csrf_token': tok})
    assert c.get(f'/attendance/api/daily-summary?assignment_id={ids["caa"]}&date={ids["date"]}').status_code == 403
    assert c.get(f'/attendance/api/report/weekly?assignment_id={ids["caa"]}&week_id={ids["week"]}').status_code == 403
    assert c.get(f'/attendance/api/report/termly?assignment_id={ids["caa"]}').status_code == 403
