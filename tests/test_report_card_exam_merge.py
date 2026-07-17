"""Report card: mid-term / CBT / theory are summed into one EXAM column, and
'No. in class' counts the student's own class arm."""
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment, Subject, ClassSubject,
                    AssessmentType, StudentScore)


_SEQ = [0]


def _seed(app):
    with app.app_context():
        _SEQ[0] += 1
        tag = f'RM{_SEQ[0]}'
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'{tag}-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=2, name='Second Term'); db.session.add(term); db.session.flush()
        sc = SchoolClass.query.first(); arm = ClassArm.query.first()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        # a second arm of the same class, with its own students (must NOT count)
        arm2 = ClassArm(name=f'{tag}-ArmB'); db.session.add(arm2); db.session.flush()
        caa2 = ClassArmAssignment(class_id=sc.id, arm_id=arm2.id, term_id=term.id, branch_id=bid)
        db.session.add(caa2); db.session.flush()
        subj = Subject(name=f'{tag}-Maths', is_active=True); db.session.add(subj); db.session.flush()
        cs = ClassSubject(subject_id=subj.id, class_id=sc.id, arm_id=arm.id, term_id=term.id, is_active=True)
        db.session.add(cs); db.session.flush()
        defs = [('CA1', 5, 1), ('CA2', 5, 2), ('HA', 5, 3), ('MID', 10, 4), ('CBT', 30, 5), ('EXAM', 40, 6)]
        ats = {}
        for sn, mx, o in defs:
            a = AssessmentType.query.filter_by(short_name=sn).first() or AssessmentType(
                name=sn, short_name=sn, max_score=mx, order=o, is_active=True)
            if a.id is None:
                db.session.add(a); db.session.flush()
            ats[sn] = a
        st = Student(student_id=f'{tag}-1', first_name='Ada', surname='Obi', gender='Female',
                     is_active=True, branch_id=bid)
        db.session.add(st); db.session.flush()
        db.session.add(StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True))
        # one more student in the SAME arm; two in the OTHER arm
        for i in range(1):
            s = Student(student_id=f'{tag}a{i}', first_name='B', surname='C', gender='Male', is_active=True, branch_id=bid)
            db.session.add(s); db.session.flush()
            db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id, is_active=True))
        for i in range(2):
            s = Student(student_id=f'{tag}b{i}', first_name='D', surname='E', gender='Male', is_active=True, branch_id=bid)
            db.session.add(s); db.session.flush()
            db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa2.id, is_active=True))
        scores = {'CA1': 5, 'CA2': 5, 'HA': 5, 'MID': 8, 'CBT': 22, 'EXAM': 30}
        for sn, v in scores.items():
            db.session.add(StudentScore(student_id=st.id, class_subject_id=cs.id,
                                        assessment_type_id=ats[sn].id, score=v))
        db.session.commit()
        return dict(term=term.id, student=st.id)


def test_exam_columns_merged_and_arm_count(app):
    from utils.report_card import build_report_card
    ids = _seed(app)
    with app.app_context():
        _, rc = build_report_card(ids['student'], ids['term'])
        labels = [c['label'] for c in rc['columns']]
        # mid-term/CBT/theory collapse to a single EXAM column, placed last
        assert 'MID' not in labels and 'CBT' not in labels
        assert labels[-1] == 'EXAM' and labels.count('EXAM') == 1
        assert set(labels[:-1]) <= {'CA1', 'CA2', 'CA3', 'HA'}
        row = rc['subjects'][0]
        # EXAM cell (last) = MID + CBT + Theory = 8 + 22 + 30 = 60
        assert row['cells'][-1] == 60
        assert row['total'] == 75            # 5+5+5+8+22+30 (CA3 unscored)
        # No. in class = this arm's roster (2), not the whole class (4)
        assert rc['no_in_class'] == 2


def test_scores_obtainable_is_100_per_subject(app):
    """Total obtainable = 100 × number of subjects, regardless of how the
    assessment components sum (here CA/HA/MID/CBT/EXAM add to 95, not 100)."""
    from utils.report_card import build_report_card
    ids = _seed(app)
    with app.app_context():
        _, rc = build_report_card(ids['student'], ids['term'])
        assert rc['total_subjects'] == 1
        assert rc['scores_obtainable'] == 100          # 100 × 1 subject
        # percentage uses the 100-per-subject denominator
        assert rc['average_pct'] == round(rc['scores_obtained'] / 100 * 100, 2)


def test_attendance_filled_from_records(app):
    import datetime as _dt
    from models import Week, Attendance, StudentEnrollment
    from utils.report_card import build_report_card
    ids = _seed(app)
    with app.app_context():
        enr = StudentEnrollment.query.filter_by(student_id=ids['student'], is_active=True).first()
        wk = Week(term_id=ids['term'], week_number=1,
                  start_date=_dt.date(2025, 1, 6), end_date=_dt.date(2025, 1, 10))
        db.session.add(wk); db.session.flush()
        # 3 school days: (present,present), (present,absent), (absent,absent)
        days = [(_dt.date(2025, 1, 6), True, True),
                (_dt.date(2025, 1, 7), True, False),
                (_dt.date(2025, 1, 8), False, False)]
        for d, m, a in days:
            db.session.add(Attendance(enrollment_id=enr.id, week_id=wk.id, date=d,
                                      morning_present=m, afternoon_present=a))
        db.session.commit()
        _, rc = build_report_card(ids['student'], ids['term'])
        assert rc['attendance_present'] == 3        # 2 + 1 + 0 sessions
        assert rc['attendance_days_present'] == 2
        assert rc['attendance_days_opened'] == 3
        assert rc['attendance_pct'] == 50.0         # 3 of 6 sessions
