"""Attendance analytics never shows more than 100%, and 'Most improved' only
compares against a previous term whose register was actually taken."""
from datetime import date, timedelta

from models import (db, Branch, Student, ClassArmAssignment, SchoolClass, ClassArm,
                    Term, AcademicSession, StudentEnrollment, Week, Attendance, Holiday)


def _term(sess, n, monday, tag):
    t = Term(session_id=sess.id, term_number=n, name=f'CapT{tag}{n}', is_active=False,
             start_date=monday, end_date=monday + timedelta(days=4))
    db.session.add(t); db.session.flush()
    w = Week(term_id=t.id, week_number=1, start_date=monday, end_date=monday + timedelta(days=6))
    db.session.add(w); db.session.flush()
    sc = SchoolClass(name=f'CapC{tag}{n}', level=1); arm = ClassArm(name=f'CapA{tag}{n}', is_active=True)
    db.session.add_all([sc, arm]); db.session.flush()
    caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=t.id, branch_id=Branch.get_default().id)
    db.session.add(caa); db.session.flush()
    return t, w, caa


def _mark(en, w, d, m=True, a=True):
    db.session.add(Attendance(enrollment_id=en.id, week_id=w.id, date=d, morning_present=m, afternoon_present=a))


def test_weekend_and_holiday_marks_do_not_push_past_100(app):
    from utils import attendance_analytics as AA
    with app.app_context():
        sess = AcademicSession(name='CapS1', is_active=False); db.session.add(sess); db.session.flush()
        mon = date(2025, 5, 5)
        t, w, caa = _term(sess, 1, mon, 'W')
        db.session.add(Holiday(term_id=t.id, date=mon + timedelta(days=4), reason='Break'))
        st = Student(student_id='CAPW1', first_name='Ada', surname='Cap', gender='Female',
                     is_active=True, branch_id=Branch.get_default().id)
        db.session.add(st); db.session.flush()
        en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
        db.session.add(en); db.session.flush()
        for i in range(7):            # Mon–Sun, including the Friday holiday and the weekend
            _mark(en, w, mon + timedelta(days=i))
        db.session.commit()
        data = AA.build(t, [caa], use_cache=False)
        assert data['kpis']['overall'] == 100.0
        assert data['class_rank'][0]['percentage'] == 100.0
        assert all(x['percentage'] <= 100 for x in data['trend'] + data['heatmap'])
        from utils.calculations import get_termly_attendance_summary
        s = get_termly_attendance_summary(caa.id, t.id)
        assert s['students'][0]['percentage'] <= 100 and s['students'][0]['termly_total'] == 8


def test_most_improved_ignores_untaken_previous_register(app):
    from utils import attendance_analytics as AA
    with app.app_context():
        sess = AcademicSession(name='CapS2', is_active=False); db.session.add(sess); db.session.flush()
        t1, w1, c1 = _term(sess, 1, date(2025, 1, 6), 'I')     # register never taken
        t2, w2, c2 = _term(sess, 2, date(2025, 5, 5), 'I')
        bid = Branch.get_default().id
        a = Student(student_id='CAPI1', first_name='Untaken', surname='Cap', gender='Male', is_active=True, branch_id=bid)
        b = Student(student_id='CAPI2', first_name='Real', surname='Cap', gender='Male', is_active=True, branch_id=bid)
        db.session.add_all([a, b]); db.session.flush()
        # Last term: a's class never marked; b in a second class that was marked (absent Mon–Thu).
        sc2 = SchoolClass(name='CapCIx', level=1); arm2 = ClassArm(name='CapAIx', is_active=True)
        db.session.add_all([sc2, arm2]); db.session.flush()
        c1m = ClassArmAssignment(class_id=sc2.id, arm_id=arm2.id, term_id=t1.id, branch_id=bid)
        db.session.add(c1m); db.session.flush()
        ea1 = StudentEnrollment(student_id=a.id, class_arm_assignment_id=c1.id, is_active=True)
        eb1 = StudentEnrollment(student_id=b.id, class_arm_assignment_id=c1m.id, is_active=True)
        db.session.add_all([ea1, eb1]); db.session.flush()
        for i in range(5):
            _mark(eb1, w1, date(2025, 1, 6) + timedelta(days=i), m=(i == 4), a=(i == 4))
        # This term both are present every day.
        ea2 = StudentEnrollment(student_id=a.id, class_arm_assignment_id=c2.id, is_active=True)
        eb2 = StudentEnrollment(student_id=b.id, class_arm_assignment_id=c2.id, is_active=True)
        db.session.add_all([ea2, eb2]); db.session.flush()
        for en in (ea2, eb2):
            for i in range(5):
                _mark(en, w2, date(2025, 5, 5) + timedelta(days=i))
        db.session.commit()
        data = AA.build(t2, [c2], use_cache=False)
        names = {x['name']: x for x in data['most_improved']}
        assert not any('Untaken' in n for n in names)
        real = next(x for n, x in names.items() if 'Real' in n)
        assert real['from'] == 20.0 and real['to'] == 100.0 and real['delta'] == 80.0


def test_analytics_lists_students_below_target_and_class_counts(app):
    from utils import attendance_analytics as AA
    with app.app_context():
        sess = AcademicSession(name='CapS3', is_active=False); db.session.add(sess); db.session.flush()
        mon = date(2025, 5, 5)
        t, w, caa = _term(sess, 1, mon, 'B')
        bid = Branch.get_default().id
        rates = {'Full': 5, 'Risk': 3, 'Low': 1}       # present days out of 5
        for nm, n in rates.items():
            st = Student(student_id='CAPB' + nm, first_name=nm, surname='Cap', gender='Male', is_active=True, branch_id=bid)
            db.session.add(st); db.session.flush()
            en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
            db.session.add(en); db.session.flush()
            for i in range(n):
                _mark(en, w, mon + timedelta(days=i))
        db.session.commit()
        data = AA.build(t, [caa], use_cache=False)
        names = [s['name'] for s in data['below_list']]
        assert len(names) == 2 and 'Low' in names[0] and 'Risk' in names[1]   # lowest first
        assert data['kpis']['below_threshold'] == 2 and data['kpis']['chronic'] == 1
        row = data['class_rank'][0]
        assert row['below'] == 2 and row['chronic'] == 1
        assert data['most_declined'] == [] and data['kpis']['prev_overall'] is None
