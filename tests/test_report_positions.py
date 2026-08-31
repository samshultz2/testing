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


def test_position_in_arm_is_per_arm(app):
    """A class with two arms ranks each arm independently: every arm has its own
    #1, while position_in_class spans the whole class."""
    from utils.report_card import compute_term_summaries
    with app.app_context():
        bid = Branch.get_default().id
        sess = AcademicSession(name='ARM-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='ARM-Term'); db.session.add(term); db.session.flush()
        sc = SchoolClass(name='ARM-Class', level=99); db.session.add(sc); db.session.flush()
        arm_a = ClassArm(name='ARM-A'); arm_b = ClassArm(name='ARM-B')
        db.session.add_all([arm_a, arm_b]); db.session.flush()
        subj = Subject(name='ARM-Maths', is_active=True); db.session.add(subj); db.session.flush()
        # reuse an existing active assessment type — creating a new global one
        # would leak into other tests' report-card columns.
        at = AssessmentType.query.filter_by(is_active=True).first()
        if not at:
            at = AssessmentType(name='ARM-Exam', short_name='AX', max_score=100, order=1, is_active=True)
            db.session.add(at); db.session.flush()
        # class-wide subject (arm_id NULL) so both arms take it
        cs = ClassSubject(subject_id=subj.id, class_id=sc.id, arm_id=None, term_id=term.id, is_active=True)
        db.session.add(cs); db.session.flush()
        marks = {}
        for arm, scores in ((arm_a, (70, 40)), (arm_b, (90, 30))):
            caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
            db.session.add(caa); db.session.flush()
            for i, score in enumerate(scores):
                s = Student(student_id=f'ARM-{arm.name}-{i}', first_name='A', surname=arm.name,
                            gender='Male', is_active=True, branch_id=bid)
                db.session.add(s); db.session.flush()
                db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id, is_active=True))
                db.session.add(StudentScore(student_id=s.id, class_subject_id=cs.id,
                                            assessment_type_id=at.id, score=score))
                marks[(arm.name, score)] = s.id
        db.session.commit()

        compute_term_summaries(term.id, sc.id)

        def ts(sid):
            return TermSummary.query.filter_by(student_id=sid, term_id=term.id).first()
        # Each arm's top scorer is 1st IN ITS ARM…
        assert ts(marks[('ARM-A', 70)]).position_in_arm == 1
        assert ts(marks[('ARM-A', 40)]).position_in_arm == 2
        assert ts(marks[('ARM-B', 90)]).position_in_arm == 1
        assert ts(marks[('ARM-B', 30)]).position_in_arm == 2
        # …but class-wide the 90 beats the 70 (positions span both arms).
        assert ts(marks[('ARM-B', 90)]).position_in_class == 1
        assert ts(marks[('ARM-A', 70)]).position_in_class == 2


def test_competition_ranking_ties():
    from utils.report_card import _assign_ranks
    rows = [{'average': 90}, {'average': 80}, {'average': 80}, {'average': 50}]
    _assign_ranks(rows, 'pos')
    assert sorted(r['pos'] for r in rows) == [1, 2, 2, 4]   # ties share a rank


def test_report_card_pdf_download(app):
    from config import Config
    from models import Student
    from utils.report_card import compute_term_summaries
    from tests.conftest import login_token
    term_id, class_id = _setup(app)
    with app.app_context():
        compute_term_summaries(term_id, class_id)
        sid = Student.query.filter_by(student_id='RC1').first().id
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    r = c.get(f'/subjects/report-card/{sid}/pdf?term_id={term_id}')
    assert r.status_code == 200
    assert r.headers['Content-Type'] == 'application/pdf'
    assert r.data[:5] == b'%PDF-'
