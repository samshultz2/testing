"""Holiday date ranges + whole-week batch attendance marking."""
import re
from datetime import date

from config import Config
from models import (db, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, StudentEnrollment, Student, Week, Holiday,
                    Attendance)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    return c


def _ptoken(c, url):
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get(url).get_data(as_text=True)).group(1)


def _term(app, name='HOL 24/25'):
    with app.app_context():
        s = AcademicSession.query.filter_by(name=name).first() or AcademicSession(name=name)
        db.session.add(s); db.session.flush()
        t = Term.query.filter_by(session_id=s.id, term_number=1).first()
        if not t:
            t = Term(session_id=s.id, term_number=1, name='First Term')
            db.session.add(t); db.session.flush()
        db.session.commit()
        return t.id


def test_holiday_range_creates_one_per_weekday(app):
    tid = _term(app)
    c = _admin(app)
    # Mon 25 May 2026 -> Fri 29 May 2026 is 5 weekdays; range incl a weekend tail.
    c.post(f'/academics/terms/{tid}/holidays/add',
           data={'date': '2026-05-25', 'end_date': '2026-05-31',  # Sun included
                 'reason': 'Mid-term Break', 'holiday_type': 'Mid-term Break',
                 '_csrf_token': _ptoken(c, '/academics/terms/%d' % tid)})
    with app.app_context():
        days = Holiday.query.filter_by(term_id=tid, reason='Mid-term Break').all()
        got = sorted(h.date for h in days)
        assert got == [date(2026, 5, 25), date(2026, 5, 26), date(2026, 5, 27),
                       date(2026, 5, 28), date(2026, 5, 29)]   # weekend skipped


def test_holiday_single_day_still_works(app):
    tid = _term(app, name='HOL SINGLE')
    c = _admin(app)
    c.post(f'/academics/terms/{tid}/holidays/add',
           data={'date': '2026-06-01', 'reason': 'Eid', '_csrf_token':
                 _ptoken(c, '/academics/terms/%d' % tid)})
    with app.app_context():
        assert Holiday.query.filter_by(term_id=tid, reason='Eid').count() == 1


def _class_week(app):
    with app.app_context():
        s = AcademicSession.query.filter_by(name='WK 24/25').first() or AcademicSession(name='WK 24/25')
        db.session.add(s); db.session.flush()
        t = Term.query.filter_by(session_id=s.id, term_number=1).first() or \
            Term(session_id=s.id, term_number=1, name='First Term')
        db.session.add(t); db.session.flush()
        wk = Week.query.filter_by(term_id=t.id, week_number=1).first() or Week(
            term_id=t.id, week_number=1,
            start_date=date(2026, 5, 18), end_date=date(2026, 5, 22))
        db.session.add(wk); db.session.flush()
        sc = SchoolClass.query.filter_by(name='WKCLASS').first() or SchoolClass(name='WKCLASS', level=1)
        db.session.add(sc); db.session.flush()
        arm = ClassArm.query.filter_by(name='WKA').first() or ClassArm(name='WKA', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = ClassArmAssignment.query.filter_by(class_id=sc.id, arm_id=arm.id, term_id=t.id).first() or \
            ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=t.id)
        db.session.add(caa); db.session.flush()
        eids = []
        for n in ('WKS1', 'WKS2'):
            st = Student.query.filter_by(student_id=n).first() or Student(
                student_id=n, first_name=n, surname='Wk', gender='Male', is_active=True)
            db.session.add(st); db.session.flush()
            en = StudentEnrollment.query.filter_by(student_id=st.id, class_arm_assignment_id=caa.id).first() or \
                StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
            db.session.add(en); db.session.flush()
            eids.append(en.id)
        db.session.commit()
        return t.id, caa.id, wk.id, eids


def test_week_batch_save_split_sessions(app):
    tid, aid, wid, eids = _class_week(app)
    c = _admin(app)
    tok = _ptoken(c, f'/attendance/week?term_id={tid}&assignment_id={aid}&week_id={wid}&sessions=split')
    # Student present in the morning but absent in the afternoon on Monday.
    data = {'term_id': tid, 'assignment_id': aid, 'week_id': wid, 'sessions': 'split',
            '_csrf_token': tok, f'am_{eids[0]}_2026-05-18': 'on'}  # no pm_ -> afternoon absent
    c.post('/attendance/week/save', data=data, follow_redirects=True)
    with app.app_context():
        rec = Attendance.query.filter_by(enrollment_id=eids[0], date=date(2026, 5, 18)).first()
        assert rec.morning_present is True
        assert rec.afternoon_present is False


def test_week_batch_save(app):
    tid, aid, wid, eids = _class_week(app)
    c = _admin(app)
    tok = _ptoken(c, f'/attendance/week?term_id={tid}&assignment_id={aid}&week_id={wid}')
    # Student 1 present Mon+Tue only; student 2 absent all week (no checkboxes).
    data = {'term_id': tid, 'assignment_id': aid, 'week_id': wid, '_csrf_token': tok,
            f'p_{eids[0]}_2026-05-18': 'on', f'p_{eids[0]}_2026-05-19': 'on'}
    r = c.post('/attendance/week/save', data=data, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        recs = {(a.enrollment_id, a.date.isoformat()): a for a in Attendance.query.filter(
            Attendance.enrollment_id.in_(eids)).all()}
        # 2 students x 5 school days = 10 rows written
        assert len(recs) == 10
        assert recs[(eids[0], '2026-05-18')].morning_present is True
        assert recs[(eids[0], '2026-05-20')].morning_present is False   # not ticked
        assert recs[(eids[1], '2026-05-18')].afternoon_present is False  # absent all week
