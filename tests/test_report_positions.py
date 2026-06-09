"""compute_term_summaries ranks students and persists positions/totals."""
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment, Subject,
                    ClassSubject, AssessmentType, StudentScore, TermSummary)


def _setup(app):
    with app.app_context():
        if Student.query.filter_by(student_id='RC1').first():
            t = Term.query.filter_by(name='RC-Term').first()
            sc = ClassArmAssignment.query.filter_by(term_id=t.id).first().school_class
            return t.id, sc.id
        bid = Branch.get_default().id
        sess = AcademicSession(name='RC-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='RC-Term'); db.session.add(term); db.session.flush()
        sc = SchoolClass.query.first(); arm = ClassArm.query.first()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        subj = Subject.query.first() or Subject(name='Maths', is_active=True)
        if subj.id is None:
            db.session.add(subj); db.session.flush()
        cs = ClassSubject(subject_id=subj.id, class_id=sc.id, arm_id=arm.id, term_id=term.id, is_active=True)
        db.session.add(cs); db.session.flush()
        at = AssessmentType.query.filter_by(is_active=True).first() or \
            AssessmentType(name='Exam', max_score=100, order=1, is_active=True)
        if at.id is None:
            db.session.add(at); db.session.flush()
        # two students, different scores
        hi = Student(student_id='RC1', first_name='Hi', surname='Score', gender='Male', is_active=True, branch_id=bid)
        lo = Student(student_id='RC2', first_name='Lo', surname='Score', gender='Female', is_active=True, branch_id=bid)
        db.session.add_all([hi, lo]); db.session.flush()
        for s in (hi, lo):
            db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id, is_active=True))
        db.session.add(StudentScore(student_id=hi.id, class_subject_id=cs.id, assessment_type_id=at.id, score=85))
        db.session.add(StudentScore(student_id=lo.id, class_subject_id=cs.id, assessment_type_id=at.id, score=40))
        db.session.commit()
        return term.id, sc.id


def test_compute_positions(app):
    term_id, class_id = _setup(app)
    from utils.report_card import compute_term_summaries
    with app.app_context():
        n = compute_term_summaries(term_id, class_id)
        assert n == 2
        hi = Student.query.filter_by(student_id='RC1').first()
        lo = Student.query.filter_by(student_id='RC2').first()
        ts_hi = TermSummary.query.filter_by(student_id=hi.id, term_id=term_id).first()
        ts_lo = TermSummary.query.filter_by(student_id=lo.id, term_id=term_id).first()
        assert ts_hi.position_in_class == 1 and ts_lo.position_in_class == 2
        assert ts_hi.average_score == 85 and ts_lo.average_score == 40
        assert ts_hi.subjects_passed == 1 and ts_lo.subjects_failed == 1


def test_competition_ranking_ties():
    from utils.report_card import _assign_ranks
    rows = [{'average': 90}, {'average': 80}, {'average': 80}, {'average': 50}]
    _assign_ranks(rows, 'pos')
    assert sorted(r['pos'] for r in rows) == [1, 2, 2, 4]   # ties share a rank
