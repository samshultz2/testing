"""teacher_scorecard()/subject_scorecard() (the drill-downs behind the
Institution Analytics leagues) used to run a StudentEnrollment query AND a
StudentScore query per class-subject row in their main loop, and — worse —
the term-trend section fetched EVERY ClassSubject in the WHOLE SCHOOL per
term (unscoped) and then ran a StudentScore query per class-subject per term.
Regression: none of this scales with how many classes a teacher/subject
spans."""
import re
from sqlalchemy import event
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment, Subject,
                    ClassSubject, AssessmentType, StudentScore)

_CLASS_COUNT = 12
_SEQ = [0]


def _count_selects(app, table, fn):
    pattern = re.compile(r'^select\b.*\bfrom\s+' + re.escape(table) + r'\b',
                         re.IGNORECASE | re.DOTALL)
    counts = {'n': 0}

    def before(conn, cursor, statement, params, context, executemany):
        if pattern.match(statement):
            counts['n'] += 1
    with app.app_context():
        engine = db.engine
    event.listen(engine, 'before_cursor_execute', before)
    try:
        fn()
    finally:
        event.remove(engine, 'before_cursor_execute', before)
    return counts['n']


def _seed(app):
    """One teacher (Mr Scale) teaching Maths in _CLASS_COUNT different
    class-arms, each with a couple of students and scores — big enough that a
    per-class-subject query shows up clearly in the count."""
    with app.app_context():
        _SEQ[0] += 1
        tag = f'SCN{_SEQ[0]}'
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'{tag}-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'{tag}-Term')
        db.session.add(term); db.session.flush()
        maths = Subject(name=f'{tag}-Maths', is_active=True)
        db.session.add(maths); db.session.flush()
        at = AssessmentType.query.filter_by(short_name='CA1').first() or AssessmentType(
            name='1st CA', short_name='CA1', max_score=100, order=1, is_active=True)
        if at.id is None:
            db.session.add(at); db.session.flush()
        arm = ClassArm.default()

        subject_id = maths.id
        for i in range(_CLASS_COUNT):
            sc = SchoolClass(name=f'{tag}-C{i}', level=1, section='junior', is_active=True)
            db.session.add(sc); db.session.flush()
            caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
            db.session.add(caa); db.session.flush()
            cs = ClassSubject(subject_id=maths.id, class_id=sc.id, arm_id=arm.id,
                              term_id=term.id, teacher_name='Mr Scale', is_active=True)
            db.session.add(cs); db.session.flush()
            for j in range(2):
                st = Student(student_id=f'{tag}-{i}-{j}', first_name=f'S{j}', surname=f'C{i}',
                            gender='Male', is_active=True, branch_id=bid)
                db.session.add(st); db.session.flush()
                db.session.add(StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id,
                                                 is_active=True))
                db.session.add(StudentScore(student_id=st.id, class_subject_id=cs.id,
                                            assessment_type_id=at.id, score=60 + i))
        db.session.commit()
        return term.id, subject_id


def test_teacher_scorecard_does_not_scale_with_class_count(app):
    term_id, subject_id = _seed(app)
    from utils.results_analytics_org import teacher_scorecard

    with app.app_context():
        n = _count_selects(app, 'student_scores',
                           lambda: teacher_scorecard(term_id, 'Mr Scale', None))
        assert n < _CLASS_COUNT, f'{n} StudentScore SELECTs for {_CLASS_COUNT} class-subjects — looks like an N+1'

        sc = teacher_scorecard(term_id, 'Mr Scale', None)
        assert len(sc['rows']) == _CLASS_COUNT
        assert sc['summary']['entries'] == _CLASS_COUNT * 2


def test_subject_scorecard_does_not_scale_with_class_count(app):
    term_id, subject_id = _seed(app)
    from utils.results_analytics_org import subject_scorecard

    with app.app_context():
        n = _count_selects(app, 'student_scores',
                           lambda: subject_scorecard(term_id, subject_id, None))
        assert n < _CLASS_COUNT, f'{n} StudentScore SELECTs for {_CLASS_COUNT} class-subjects — looks like an N+1'

        sc = subject_scorecard(term_id, subject_id, None)
        assert len(sc['rows']) == _CLASS_COUNT
        assert sc['summary']['entries'] == _CLASS_COUNT * 2
