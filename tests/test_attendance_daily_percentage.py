"""Daily attendance % counts both sessions: (AM present + PM present) / (2 x
students) — a day with 29 AM / 27 PM of 31 is 90.32%, not the AM-only 93.55%."""
import uuid
from datetime import date

from models import (db, Branch, Student, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, StudentEnrollment, Attendance, Week)
from utils.calculations import get_daily_attendance_summary


def test_daily_percentage_uses_morning_and_afternoon(app):
    tag = uuid.uuid4().hex[:5].upper()
    with app.app_context():
        term = Term.query.filter_by(is_active=True).first()
        if not term:
            sess = AcademicSession(name=f'DP{tag}', is_active=True); db.session.add(sess); db.session.flush()
            term = Term(session_id=sess.id, term_number=1, name='First Term', is_active=True)
            db.session.add(term); db.session.flush()
        sc = SchoolClass(name=f'DPC{tag}', level=3); arm = ClassArm(name=f'DPA{tag}', is_active=True)
        db.session.add_all([sc, arm]); db.session.flush()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=Branch.get_default().id)
        db.session.add(caa); db.session.flush()
        day = date(2026, 11, 9)
        day2 = date(2026, 11, 10)
        wk = Week(term_id=term.id, week_number=90, start_date=day, end_date=day2)
        db.session.add(wk); db.session.flush()
        for i in range(31):
            st = Student(student_id=f'DP{tag}{i:02d}', first_name='S', surname=f'Dp{i}', gender='Male', is_active=True)
            db.session.add(st); db.session.flush()
            en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
            db.session.add(en); db.session.flush()
            db.session.add(Attendance(enrollment_id=en.id, week_id=wk.id, date=day, morning_present=i >= 2, afternoon_present=i >= 4))
            db.session.add(Attendance(enrollment_id=en.id, week_id=wk.id, date=day2, morning_present=i >= 2, afternoon_present=i >= 2))
        db.session.commit()
        s = get_daily_attendance_summary(caa.id, day)
        assert (s['morning_present'], s['afternoon_present']) == (29, 27)
        assert s['attendance_percentage'] == 90.32
        s2 = get_daily_attendance_summary(caa.id, day2)
        assert s2['attendance_percentage'] == 93.55          # 29 AM / 29 PM — a different day, rightly higher
        # Weekly (Mon + Tue): (29 + 27 + 29 + 29) / (31 x 4 sessions) = 114 / 124 = 91.94%
        from utils.calculations import get_weekly_attendance_summary
        w = get_weekly_attendance_summary(caa.id, wk.id)
        ct = w.get('class_totals') or w
        assert ct['total_morning'] == 58 and ct['total_afternoon'] == 56
        assert ct['weekly_percentage'] == 91.94
