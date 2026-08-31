"""Attendance-integrity guard: the save endpoint must reject dates a register
can't legitimately be taken for (future / out-of-term / weekend / holiday),
closing the back-dating attendance-fraud vector.
"""
from datetime import date, timedelta
from config import Config
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment, Attendance, Week)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _pt(c):
    import re
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/').get_data(as_text=True)).group(1)


def _setup(app):
    """A term spanning a known school week, one enrolled student."""
    with app.app_context():
        if Student.query.filter_by(student_id='AT1').first():
            t = Term.query.filter_by(name='AT-Term').first()
            caa = ClassArmAssignment.query.filter_by(term_id=t.id).first()
            en = StudentEnrollment.query.filter_by(class_arm_assignment_id=caa.id).first()
            wk = Week.query.filter_by(term_id=t.id).first()
            return dict(term=t.id, asg=caa.id, en=en.id, week=wk.id)
        bid = Branch.get_default().id
        sess = AcademicSession(name='AT-Sess'); db.session.add(sess); db.session.flush()
        # Term window: a comfortably-past month so "today" is inside it.
        start = date.today() - timedelta(days=30)
        end = date.today() + timedelta(days=30)
        term = Term(session_id=sess.id, term_number=1, name='AT-Term',
                    start_date=start, end_date=end, is_active=True)
        db.session.add(term); db.session.flush()
        # A single wide Week over the term (week_id is NOT NULL on Attendance).
        wk = Week(term_id=term.id, week_number=1, start_date=start, end_date=end)
        db.session.add(wk); db.session.flush()
        sc = SchoolClass.query.first(); arm = ClassArm.query.first()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        s = Student(student_id='AT1', first_name='At', surname='One', gender='Male',
                    is_active=True, branch_id=bid)
        db.session.add(s); db.session.flush()
        en = StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id, is_active=True)
        db.session.add(en); db.session.commit()
        return dict(term=term.id, asg=caa.id, en=en.id, week=wk.id)


def _last_weekday(offset_days):
    """A date `offset_days` from today, nudged onto a weekday."""
    d = date.today() + timedelta(days=offset_days)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _save(c, ids, d):
    return c.post('/attendance/mark/save', data={
        'assignment_id': ids['asg'], 'date': d.isoformat(), 'session_type': 'morning',
        'week_id': ids['week'], 'present[]': [ids['en']], '_csrf_token': _pt(c)},
        follow_redirects=True)


def test_future_date_rejected(app):
    ids = _setup(app)
    c = _admin(app)
    future = _last_weekday(60)                          # beyond term end + future
    _save(c, ids, future)
    with app.app_context():
        assert Attendance.query.filter_by(enrollment_id=ids['en'], date=future).first() is None


def test_weekend_date_rejected(app):
    ids = _setup(app)
    c = _admin(app)
    # Nearest past Saturday (in-term, but not a school day).
    d = date.today()
    while d.weekday() != 5:
        d -= timedelta(days=1)
    _save(c, ids, d)
    with app.app_context():
        assert Attendance.query.filter_by(enrollment_id=ids['en'], date=d).first() is None


def test_valid_in_term_school_day_is_accepted(app):
    ids = _setup(app)
    c = _admin(app)
    d = _last_weekday(-3)                               # a recent weekday, in term
    _save(c, ids, d)
    with app.app_context():
        assert Attendance.query.filter_by(enrollment_id=ids['en'], date=d).first() is not None
