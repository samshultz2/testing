"""Attendance JSON API (React offline pilot): roster read + idempotent mark write."""
import re
from datetime import date, timedelta

from config import Config
from models import (db, Branch, User, Student, ClassArmAssignment, SchoolClass,
                    ClassArm, Term, AcademicSession, StudentEnrollment, Week, Attendance, Holiday)
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
        # A guaranteed school day (weekday, no holidays in this fixture) within
        # the week — marking endpoints now reject weekends/holidays.
        school_date = wk.start_date
        while school_date.weekday() >= 5 and school_date < wk.end_date:
            school_date += timedelta(days=1)
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
        return dict(caa=caa.id, eids=eids, date=school_date.isoformat(), bid=bid, week=wk.id)


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
        d = date.fromisoformat(ids['date'])
        present = Attendance.query.filter_by(enrollment_id=ids['eids'][0], date=d).first()
        absent = Attendance.query.filter_by(enrollment_id=ids['eids'][1], date=d).first()
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


def test_mark_rejects_holiday(app):
    ids = _setup(app)
    with app.app_context():
        caa = ClassArmAssignment.query.get(ids['caa'])
        d = date.fromisoformat(ids['date'])
        if not Holiday.query.filter_by(term_id=caa.term_id, date=d).first():
            db.session.add(Holiday(term_id=caa.term_id, date=d, reason='AA-Test Holiday',
                                   holiday_type='Public Holiday'))
            db.session.commit()
    c, tok = _admin(app)
    # roster flags it as a non-school day with the reason
    j = c.get(f'/attendance/api/roster?assignment_id={ids["caa"]}&date={ids["date"]}').get_json()
    assert j['school_day'] is False and j['holiday']['reason'] == 'AA-Test Holiday'
    # and saving is rejected
    m = c.post('/attendance/api/mark', headers={'X-CSRFToken': tok},
               json={'assignment_id': ids['caa'], 'date': ids['date'], 'present': []})
    assert m.status_code == 400
    # clean up so the shared session DB stays a normal school day for later tests
    with app.app_context():
        caa = ClassArmAssignment.query.get(ids['caa'])
        Holiday.query.filter_by(term_id=caa.term_id, date=date.fromisoformat(ids['date'])).delete()
        db.session.commit()


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
    assert isinstance(j['school_days'], list)
    # headline + totals the React screen renders must all be present
    for k in ('total_students', 'school_days_count', 'times_opened'):
        assert k in j
    for k in ('total_morning', 'total_afternoon', 'total_attendance',
              'male_attendance', 'female_attendance', 'weekly_percentage'):
        assert k in j['class_totals']
    for k in ('weekly_morning', 'weekly_afternoon', 'weekly_total', 'gender', 'daily'):
        assert k in j['students'][0]


def test_termly_report_serialises_weeks(app):
    ids = _setup(app)
    c, _ = _admin(app)
    r = c.get(f'/attendance/api/report/termly?assignment_id={ids["caa"]}')
    assert r.status_code == 200
    j = r.get_json()
    # weeks must be JSON-friendly dicts, not Week objects
    assert all(set(w) == {'id', 'number'} for w in j['weeks'])
    # every stat/total the React termly screen renders must be present
    for k in ('total_students', 'total_male_students', 'total_female_students', 'weekly_totals'):
        assert k in j
    for k in ('total_weeks', 'total_school_days', 'total_times_opened'):
        assert k in j['term_info']
    for k in ('total_morning', 'total_afternoon', 'total_attendance', 'male_attendance',
              'female_attendance', 'termly_average', 'termly_percentage'):
        assert k in j['class_totals']
    for k in ('gender', 'termly_morning', 'termly_afternoon', 'termly_total', 'termly_percentage', 'weekly'):
        assert k in j['students'][0]


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
    # the Excel export links the React reports point at are guarded the same way
    assert c.get(f'/attendance/weekly/export?assignment_id={ids["caa"]}&week_id={ids["week"]}').status_code == 403
    with app.app_context():
        term_id = ClassArmAssignment.query.get(ids['caa']).term_id
    assert c.get(f'/attendance/termly/export?assignment_id={ids["caa"]}&term_id={term_id}').status_code == 403


def test_weekly_termly_export_download(app):
    ids = _setup(app)
    c, _ = _admin(app)
    with app.app_context():
        term_id = ClassArmAssignment.query.get(ids['caa']).term_id
    xlsx = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    w = c.get(f'/attendance/weekly/export?assignment_id={ids["caa"]}&week_id={ids["week"]}')
    assert w.status_code == 200 and xlsx in w.content_type
    t = c.get(f'/attendance/termly/export?assignment_id={ids["caa"]}&term_id={term_id}')
    assert t.status_code == 200 and xlsx in t.content_type
