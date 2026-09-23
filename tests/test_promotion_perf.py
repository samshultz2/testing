"""Regression: /promotion/process used to run one query per student for the
average calculation, the existing-promotion-record lookup, AND the
class/rules/next-class lookup inside get_promotion_recommendation — several
hundred queries for a single class. Verifies the batched replacement computes
the exact same averages/recommendations, and that the query count no longer
scales with the number of students."""
from sqlalchemy import event

from config import Config
from models import (db, Branch, Student, AcademicSession, Term, SchoolClass,
                    ClassArm, ClassArmAssignment, StudentEnrollment, Subject,
                    ClassSubject, AssessmentType, StudentScore, PromotionRule,
                    PromotionRecord)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _get_json(c, url):
    """/promotion/process is a React-shell page that only returns JSON for a
    request flagged as a background fetch (see routes/promotion.py's
    _wants_json / utils.spa.render_or_json)."""
    return c.get(url, headers={'X-Requested-With': 'fetch'})


def _fixture(app, tag, class_level=3, n_plain_students=0):
    """A class/arm/assignment for the third term of `from_session`, with
    3 class subjects (two global, one tied to a DIFFERENT arm so it must be
    excluded from every average here), a promotion rule, and four students
    covering the rule-match / threshold-fallback / repeat / no-scores cases.
    `n_plain_students` adds extra zero-score students, to inflate class size
    for the query-count check without changing the averages under test."""
    with app.app_context():
        br = Branch.query.filter_by(code=tag).first() or Branch(name=tag, code=tag, is_active=True)
        db.session.add(br); db.session.flush()
        from_ssn = AcademicSession.query.filter_by(name=tag + '-FROM').first() \
            or AcademicSession(name=tag + '-FROM', is_active=False)
        db.session.add(from_ssn); db.session.flush()
        to_ssn = AcademicSession.query.filter_by(name=tag + '-TO').first() \
            or AcademicSession(name=tag + '-TO', is_active=False)
        db.session.add(to_ssn); db.session.flush()
        term3 = Term.query.filter_by(session_id=from_ssn.id, term_number=3).first() \
            or Term(session_id=from_ssn.id, term_number=3, name='Third Term', is_active=False)
        db.session.add(term3); db.session.flush()

        this_class = SchoolClass.query.filter_by(name=tag + '-CLS').first() \
            or SchoolClass(name=tag + '-CLS', level=class_level)
        db.session.add(this_class); db.session.flush()
        next_class = SchoolClass.query.filter_by(name=tag + '-NEXT').first() \
            or SchoolClass(name=tag + '-NEXT', level=class_level + 1)
        db.session.add(next_class); db.session.flush()

        arm = ClassArm.query.filter_by(name=tag + 'A').first() or ClassArm(name=tag + 'A', is_active=True)
        db.session.add(arm); db.session.flush()
        other_arm = ClassArm.query.filter_by(name=tag + 'B').first() or ClassArm(name=tag + 'B', is_active=True)
        db.session.add(other_arm); db.session.flush()

        caa = ClassArmAssignment.query.filter_by(class_id=this_class.id, arm_id=arm.id, term_id=term3.id).first() \
            or ClassArmAssignment(class_id=this_class.id, arm_id=arm.id, term_id=term3.id, branch_id=br.id)
        db.session.add(caa); db.session.flush()

        subj1 = Subject.query.filter_by(name=tag + '-S1').first() or Subject(name=tag + '-S1', is_active=True)
        db.session.add(subj1); db.session.flush()
        subj2 = Subject.query.filter_by(name=tag + '-S2').first() or Subject(name=tag + '-S2', is_active=True)
        db.session.add(subj2); db.session.flush()
        # A third subject tied to a DIFFERENT arm — must be excluded from
        # this arm's averages; a regression here would silently pull in
        # scores that don't belong.
        subj3 = Subject.query.filter_by(name=tag + '-S3').first() or Subject(name=tag + '-S3', is_active=True)
        db.session.add(subj3); db.session.flush()

        cs1 = ClassSubject.query.filter_by(subject_id=subj1.id, class_id=this_class.id, term_id=term3.id, arm_id=None).first() \
            or ClassSubject(subject_id=subj1.id, class_id=this_class.id, term_id=term3.id, arm_id=None, is_active=True)
        db.session.add(cs1); db.session.flush()
        cs2 = ClassSubject.query.filter_by(subject_id=subj2.id, class_id=this_class.id, term_id=term3.id, arm_id=None).first() \
            or ClassSubject(subject_id=subj2.id, class_id=this_class.id, term_id=term3.id, arm_id=None, is_active=True)
        db.session.add(cs2); db.session.flush()
        cs3 = ClassSubject.query.filter_by(subject_id=subj3.id, class_id=this_class.id, term_id=term3.id, arm_id=other_arm.id).first() \
            or ClassSubject(subject_id=subj3.id, class_id=this_class.id, term_id=term3.id, arm_id=other_arm.id, is_active=True)
        db.session.add(cs3); db.session.flush()

        # AssessmentType has no per-school/branch scoping in this app — it's a
        # single global table — and other tests (e.g. report-card rendering)
        # scan *every* active row expecting a closed set of their own making.
        # is_active=False keeps these fixture-only rows invisible to that scan
        # (StudentScore's own averaging code, which is what's actually under
        # test here, never filters on AssessmentType.is_active) while still
        # satisfying StudentScore.assessment_type_id's NOT NULL FK.
        ca = AssessmentType.query.filter_by(name=tag + '-CA').first() \
            or AssessmentType(name=tag + '-CA', short_name=tag + '-CA', max_score=40, order=1, is_active=False)
        db.session.add(ca); db.session.flush()
        exam = AssessmentType.query.filter_by(name=tag + '-EXAM').first() \
            or AssessmentType(name=tag + '-EXAM', short_name='EXAM', max_score=60, order=2, is_active=False)
        db.session.add(exam); db.session.flush()

        rule = PromotionRule.query.filter_by(from_class_id=this_class.id, to_class_id=next_class.id).first() \
            or PromotionRule(from_class_id=this_class.id, to_class_id=next_class.id,
                             min_average=75, priority=1, is_active=True)
        db.session.add(rule); db.session.flush()

        def make_student(name, ca1, exam1, ca2, exam2, has_scores=True):
            st = Student(student_id=Student.generate_student_id(), first_name=name, surname=tag,
                        gender='Male', is_active=True, branch_id=br.id)
            db.session.add(st); db.session.flush()
            en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
            db.session.add(en); db.session.flush()
            if has_scores:
                db.session.add_all([
                    StudentScore(student_id=st.id, class_subject_id=cs1.id, assessment_type_id=ca.id, score=ca1),
                    StudentScore(student_id=st.id, class_subject_id=cs1.id, assessment_type_id=exam.id, score=exam1),
                    StudentScore(student_id=st.id, class_subject_id=cs2.id, assessment_type_id=ca.id, score=ca2),
                    StudentScore(student_id=st.id, class_subject_id=cs2.id, assessment_type_id=exam.id, score=exam2),
                    # Scored on the OTHER arm's subject too — must not affect this arm's average.
                    StudentScore(student_id=st.id, class_subject_id=cs3.id, assessment_type_id=exam.id, score=999),
                ])
            return st, en

        hi, _ = make_student('Hi', 40, 50, 35, 45)      # subj1=90, subj2=80 -> avg 85 (>= rule's 75)
        mid, _ = make_student('Mid', 25, 35, 20, 35)     # subj1=60, subj2=55 -> avg 57.5 (>=50 threshold, <75 rule)
        low, _ = make_student('Low', 15, 15, 10, 10)     # subj1=30, subj2=20 -> avg 25 (<50)
        none_, _ = make_student('None', 0, 0, 0, 0, has_scores=False)  # no scores at all

        for i in range(n_plain_students):
            make_student(f'Plain{i}', 10, 10, 10, 10, has_scores=False)

        db.session.commit()
        return dict(from_session_id=from_ssn.id, to_session_id=to_ssn.id, class_id=this_class.id,
                   next_class_id=next_class.id, hi=hi.id, mid=mid.id, low=low.id, none=none_.id)


def _by_id(students, sid):
    return next(s for s in students if s['id'] == sid)


def test_averages_and_recommendations_match_every_branch(app):
    ids = _fixture(app, 'PP1')
    c = _admin(app)
    r = _get_json(c, f'/promotion/process?from_session_id={ids["from_session_id"]}'
                     f'&to_session_id={ids["to_session_id"]}&class_id={ids["class_id"]}')
    assert r.status_code == 200
    students = r.get_json()['students']
    assert len(students) == 4

    hi = _by_id(students, ids['hi'])
    assert hi['average'] == 85.0
    assert hi['recommendation']['status'] == 'promote'
    assert hi['recommendation']['to_class'] == ids['next_class_id']   # via the rule

    mid = _by_id(students, ids['mid'])
    assert mid['average'] == 57.5
    assert mid['recommendation']['status'] == 'promote'
    # Threshold fallback picks *some* class at from_class.level + 1 — same
    # ambiguous-if-several-exist lookup the app itself does
    # (SchoolClass.query.filter(level==...).first(), unscoped by name), not
    # necessarily this fixture's own "-NEXT" class if another one at that
    # level already exists in the shared test DB.
    with app.app_context():
        this_level = SchoolClass.query.get(ids['class_id']).level
        expected_next = SchoolClass.query.filter(SchoolClass.level == this_level + 1).first()
    assert mid['recommendation']['to_class'] == expected_next.id

    low = _by_id(students, ids['low'])
    assert low['average'] == 25.0
    assert low['recommendation']['status'] == 'repeat'

    none_ = _by_id(students, ids['none'])
    assert none_['average'] is None
    assert none_['recommendation']['status'] == 'unknown'


def test_existing_promotion_record_is_reported(app):
    ids = _fixture(app, 'PP2')
    with app.app_context():
        db.session.add(PromotionRecord(
            student_id=ids['hi'], from_session_id=ids['from_session_id'],
            to_session_id=ids['to_session_id'], from_class_id=ids['class_id'],
            to_class_id=ids['next_class_id'], status='promoted'))
        db.session.commit()
    c = _admin(app)
    r = _get_json(c, f'/promotion/process?from_session_id={ids["from_session_id"]}'
                     f'&to_session_id={ids["to_session_id"]}&class_id={ids["class_id"]}')
    students = r.get_json()['students']
    hi = _by_id(students, ids['hi'])
    assert hi['existing_status'] == 'promoted'
    mid = _by_id(students, ids['mid'])
    assert mid['existing_status'] is None


def test_sss3_always_graduates_regardless_of_average(app):
    """level 6 (SSS3) never goes through the rules/threshold logic at all."""
    ids = _fixture(app, 'PP3', class_level=6)
    c = _admin(app)
    r = _get_json(c, f'/promotion/process?from_session_id={ids["from_session_id"]}'
                     f'&to_session_id={ids["to_session_id"]}&class_id={ids["class_id"]}')
    students = r.get_json()['students']
    hi = _by_id(students, ids['hi'])
    low = _by_id(students, ids['low'])
    assert hi['recommendation']['status'] == 'graduated'
    assert low['recommendation']['status'] == 'graduated'
    none_ = _by_id(students, ids['none'])
    assert none_['recommendation']['status'] == 'unknown'   # no scores still wins over graduating


def test_query_count_does_not_scale_with_class_size(app):
    """The old code ran roughly (1 + subjects) queries per student for the
    average alone, plus one more for the existing-promotion lookup and at
    least one for the recommendation — a class of 24 meant hundreds of
    queries. Assert the batched version stays flat and small."""
    ids = _fixture(app, 'PP4', n_plain_students=20)   # 4 fixture students + 20 = 24 total
    c = _admin(app)

    queries = {'n': 0}
    def before(conn, cursor, statement, params, context, executemany):
        if statement.strip().lower().startswith('select'):
            queries['n'] += 1
    with app.app_context():
        engine = db.engine
    event.listen(engine, 'before_cursor_execute', before)
    try:
        r = _get_json(c, f'/promotion/process?from_session_id={ids["from_session_id"]}'
                         f'&to_session_id={ids["to_session_id"]}&class_id={ids["class_id"]}')
    finally:
        event.remove(engine, 'before_cursor_execute', before)

    assert r.status_code == 200
    assert len(r.get_json()['students']) == 24
    # Comfortably above what this page genuinely needs (a small constant
    # number of setup/lookup queries) and comfortably below what per-student
    # querying would cost (24 students x several queries each = 100+).
    assert queries['n'] < 40, f'expected a flat, small query count, got {queries["n"]} for 24 students'
