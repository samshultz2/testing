"""A student moved between arms mid-term (two enrollments in one term) must get
one merged attendance figure — not a 0% from the class they left."""
from datetime import date, timedelta

from models import (db, Student, AcademicSession, Term, SchoolClass, ClassArm, ClassArmAssignment,
                    StudentEnrollment, Week, Attendance)
from utils import timeutil


def _setup(app, tag='A'):
    with app.app_context():
        today = timeutil.today()
        mon = today - timedelta(days=today.weekday()) - timedelta(weeks=1)
        s = AcademicSession(name=f'2090/2091-{tag}', is_active=False)
        db.session.add(s); db.session.flush()
        t = Term(session_id=s.id, term_number=1, name='First Term', start_date=mon, end_date=mon + timedelta(days=60))
        db.session.add(t); db.session.flush()
        wk = Week(term_id=t.id, week_number=1, start_date=mon, end_date=mon + timedelta(days=4))
        db.session.add(wk); db.session.flush()
        c = SchoolClass(name=f'MV1{tag}', level=77); db.session.add(c); db.session.flush()
        gold = ClassArm.query.filter_by(name='MvGold').first() or ClassArm(name='MvGold'); db.session.add(gold)
        rose = ClassArm.query.filter_by(name='MvRose').first() or ClassArm(name='MvRose'); db.session.add(rose)
        db.session.flush()
        a_gold = ClassArmAssignment(class_id=c.id, arm_id=gold.id, term_id=t.id)
        a_rose = ClassArmAssignment(class_id=c.id, arm_id=rose.id, term_id=t.id)
        db.session.add_all([a_gold, a_rose]); db.session.flush()
        moved = Student(student_id=f'MOVED1{tag}', surname='Moved', first_name='Mover', gender='Female', is_active=True)
        mate = Student(student_id=f'MATE1{tag}', surname='Mate', first_name='Gold', gender='Male', is_active=True)
        db.session.add_all([moved, mate]); db.session.flush()
        # moved: first in Gold (no attendance there for them), then moved to Rose
        old = StudentEnrollment(student_id=moved.id, class_arm_assignment_id=a_gold.id, is_active=False)
        new = StudentEnrollment(student_id=moved.id, class_arm_assignment_id=a_rose.id, is_active=True)
        m = StudentEnrollment(student_id=mate.id, class_arm_assignment_id=a_gold.id, is_active=True)
        db.session.add_all([old, new, m]); db.session.flush()
        for i in range(5):
            d = mon + timedelta(days=i)
            db.session.add(Attendance(enrollment_id=m.id, week_id=wk.id, date=d, morning_present=True, afternoon_present=True))
            db.session.add(Attendance(enrollment_id=new.id, week_id=wk.id, date=d, morning_present=True, afternoon_present=True))
        db.session.commit()
        return moved.id, t.id


def test_moved_student_gets_one_merged_term_not_zero(app):
    sid, tid = _setup(app)
    from utils.attendance_profile import build_student_profile, student_term_percentage, bulk_term_percentages
    with app.app_context():
        prof = build_student_profile(sid)
        rows = [r for r in prof['terms'] if r['term_id'] == tid]
        assert len(rows) == 1
        assert rows[0]['percentage'] == 100.0
        assert 'MvRose' in rows[0]['class']
        assert student_term_percentage(sid, tid) == 100.0
        assert bulk_term_percentages([sid], tid)[sid] == 100.0


def test_rebuilding_weeks_keeps_attendance(app):
    import re
    from config import Config
    from tests.conftest import login_token
    sid, tid = _setup(app, 'B')
    with app.app_context():
        t = db.session.get(Term, tid)
        n_att = Attendance.query.join(StudentEnrollment).filter(StudentEnrollment.student_id == sid).count()
        start, end = (t.start_date - timedelta(weeks=1)).isoformat(), (t.start_date + timedelta(weeks=8)).isoformat()
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    tok = re.search(r'name="csrf-token" content="([0-9a-f]+)"', c.get('/students').get_data(as_text=True)).group(1)
    r = c.post(f'/academics/terms/{tid}/edit', headers={'X-Requested-With': 'fetch'},
               data={'start_date': start, 'end_date': end, 'regenerate_weeks': 'on', '_csrf_token': tok})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        weeks = {w.id: w for w in Week.query.filter_by(term_id=tid).all()}
        assert len(weeks) >= 9
        rows = Attendance.query.join(StudentEnrollment).filter(StudentEnrollment.student_id == sid).all()
        assert len(rows) == n_att
        for a in rows:   # every row points at a week of the term that contains its date
            w = weeks[a.week_id]
            assert w.start_date <= a.date <= w.end_date
        from utils.attendance_profile import student_term_percentage
        assert student_term_percentage(sid, tid) > 0
