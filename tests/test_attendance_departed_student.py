"""A student who leaves mid-term and is (soft-)deleted must drop out of the
attendance roster and ongoing calculations, while the attendance already
recorded while they were around is preserved (not deleted)."""
import datetime
import itertools
from models import (db, Student, Branch, ClassArm, SchoolClass, ClassArmAssignment,
                    StudentEnrollment, Attendance, Term, AcademicSession, Week)
from utils.calculations import get_daily_attendance_summary, get_termly_attendance_summary

_SEQ = itertools.count()


def _setup(app):
    with app.app_context():
        ssn = (AcademicSession.query.filter_by(is_active=True).first()
               or AcademicSession(name='ATT 25/26', is_active=True))
        db.session.add(ssn); db.session.flush()
        term = (Term.query.filter_by(is_active=True).first()
                or Term(session_id=ssn.id, term_number=1, name='First Term', is_active=True))
        db.session.add(term); db.session.flush()
        # Unique class + arm per run so this class holds only our two students
        # (the session-scoped DB is shared with other attendance tests).
        tag = next(_SEQ)
        cls = SchoolClass(name=f'ATTCLS{tag}', level=1)
        db.session.add(cls); db.session.flush()
        arm = ClassArm(name=f'ATTARM{tag}', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id)
        db.session.add(caa); db.session.flush()
        d = datetime.date(2026, 1, 12)          # a Monday
        wk = (Week.query.filter_by(term_id=term.id).first()
              or Week(term_id=term.id, week_number=1, start_date=d,
                      end_date=d + datetime.timedelta(days=4)))
        db.session.add(wk); db.session.flush()
        bid = Branch.get_default().id
        ids = []
        for _ in range(2):
            u = next(_SEQ)
            s = Student(student_id=f'ATTX{u:04d}', first_name=f'A{u}', surname='T',
                        gender='Male', is_active=True, branch_id=bid)
            db.session.add(s); db.session.flush()
            en = StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id, is_active=True)
            db.session.add(en); db.session.flush()
            db.session.add(Attendance(enrollment_id=en.id, week_id=wk.id, date=d,
                                      morning_present=True, afternoon_present=True))
            ids.append((s.id, en.id))
        db.session.commit()
        return caa.id, term.id, d, ids[0][0], ids[0][1]


def test_soft_deleted_student_excluded_but_history_kept(app):
    caa_id, term_id, d, leaver_id, leaver_en = _setup(app)
    with app.app_context():
        assert get_daily_attendance_summary(caa_id, d)['total_students'] == 2
        assert get_termly_attendance_summary(caa_id, term_id)['total_students'] == 2

        # The student leaves mid-term and is soft-deleted.
        db.session.get(Student, leaver_id).is_active = False
        db.session.commit()

        # Ongoing calculations now use the reduced class (excluding the leaver).
        assert get_daily_attendance_summary(caa_id, d)['total_students'] == 1
        assert get_termly_attendance_summary(caa_id, term_id)['total_students'] == 1

        # But the attendance recorded while they were around is preserved.
        assert Attendance.query.filter_by(enrollment_id=leaver_en).count() == 1

        # Restoring the student brings them back into the roster.
        db.session.get(Student, leaver_id).is_active = True
        db.session.commit()
        assert get_daily_attendance_summary(caa_id, d)['total_students'] == 2
