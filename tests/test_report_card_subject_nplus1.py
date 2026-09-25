"""build_report_card() (shared by the scratch-card result checker, parent
portal, and the staff report-card view) already joined Subject onto its
class_subjects query for ordering, but never eager-loaded it — so
row['subject'] = cs.subject lazy-loaded once per subject on the report
instead of reusing the join. A student taking many subjects fires one
extra Subject SELECT per subject."""
import re
from sqlalchemy import event
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment, Subject, ClassSubject,
                    AssessmentType, StudentScore)

_N_SUBJECTS = 8
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
    with app.app_context():
        _SEQ[0] += 1
        tag = f'RCS{_SEQ[0]}'
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'{tag}-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'{tag}-Term'); db.session.add(term); db.session.flush()
        sc = SchoolClass(name=f'{tag}-Class', level=1); arm = ClassArm(name=f'{tag}-Arm', is_active=True)
        db.session.add_all([sc, arm]); db.session.flush()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()

        ca1 = AssessmentType.query.filter_by(short_name='CA1').first() or AssessmentType(
            name='CA1', short_name='CA1', max_score=100, order=1, is_active=True)
        if ca1.id is None:
            db.session.add(ca1); db.session.flush()

        st = Student(student_id=f'{tag}-S1', first_name='Sub', surname='Jects',
                     gender='Female', is_active=True, branch_id=bid)
        db.session.add(st); db.session.flush()
        db.session.add(StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True))

        for i in range(_N_SUBJECTS):
            subj = Subject(name=f'{tag}-Subj{i}', is_active=True)
            db.session.add(subj); db.session.flush()
            cs = ClassSubject(subject_id=subj.id, class_id=sc.id, arm_id=arm.id,
                              term_id=term.id, is_active=True)
            db.session.add(cs); db.session.flush()
            db.session.add(StudentScore(student_id=st.id, class_subject_id=cs.id,
                                        assessment_type_id=ca1.id, score=60))
        db.session.commit()
        return dict(term=term.id, student=st.id)


def test_build_report_card_subject_lookups_do_not_scale_with_subject_count(app):
    ids = _seed(app)
    from utils.report_card import build_report_card
    with app.app_context():
        n = _count_selects(app, 'subjects',
                           lambda: build_report_card(ids['student'], ids['term']))
    assert n <= 2, (
        f'{n} subjects SELECTs for a {_N_SUBJECTS}-subject report card — looks '
        f'like an N+1 (cs.subject lazy-loaded per row instead of eager-loaded)')


def test_build_report_card_subjects_still_correct(app):
    ids = _seed(app)
    from utils.report_card import build_report_card
    with app.app_context():
        enrollment, data = build_report_card(ids['student'], ids['term'])
    assert enrollment is not None
    names = {row['subject'].name for row in data['subjects']}
    assert len(names) == _N_SUBJECTS
    assert all(row['total'] == 60 for row in data['subjects'])
