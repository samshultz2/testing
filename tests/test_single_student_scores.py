"""Single-student score entry: the API returns every assessment row (with each
row's effective max + any existing score) for one student in a class-subject,
and the save route persists all of them at once.
"""
from config import Config
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment, Subject,
                    ClassSubject, AssessmentType, StudentScore)
from tests.conftest import login_token, auth_csrf


def _setup(app):
    with app.app_context():
        # Idempotent: the suite shares one DB, so reuse the fixture if present.
        existing = AcademicSession.query.filter_by(name='SSE-Sess').first()
        if existing:
            term = Term.query.filter_by(name='SSE-Term').first()
            cs = ClassSubject.query.filter_by(term_id=term.id).first()
            caa = ClassArmAssignment.query.filter_by(term_id=term.id).first()
            a = Student.query.filter_by(student_id='SSE1').first()
            return dict(term=term.id, asg=caa.id, cs=cs.id, student=a.id)
        bid = Branch.get_default().id
        sess = AcademicSession(name='SSE-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='SSE-Term')
        db.session.add(term); db.session.flush()
        sc = SchoolClass.query.first() or SchoolClass(name='SSE-Cls', level=1)
        if sc.id is None:
            db.session.add(sc); db.session.flush()
        arm = ClassArm.query.first() or ClassArm(name='SSE-Arm', is_active=True)
        if arm.id is None:
            db.session.add(arm); db.session.flush()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        subj = Subject(name='SSE-Maths', is_active=True); db.session.add(subj); db.session.flush()
        cs = ClassSubject(subject_id=subj.id, class_id=sc.id, arm_id=arm.id,
                          term_id=term.id, is_active=True)
        db.session.add(cs); db.session.flush()
        for nm, mx, order in [('SSE-CA1', 20, 1), ('SSE-CA2', 20, 2), ('SSE-Exam', 60, 3)]:
            db.session.add(AssessmentType(name=nm, short_name=nm[:6], max_score=mx,
                                          order=order, is_active=True))
        a = Student(student_id='SSE1', first_name='Aa', surname='One', gender='Male',
                    is_active=True, branch_id=bid)
        db.session.add(a); db.session.flush()
        db.session.add(StudentEnrollment(student_id=a.id, class_arm_assignment_id=caa.id, is_active=True))
        db.session.commit()
        return dict(term=term.id, asg=caa.id, cs=cs.id, student=a.id)


def test_api_returns_all_assessment_rows(app):
    ids = _setup(app)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    r = c.get('/subjects/api/student-subject-scores', query_string={
        'term_id': ids['term'], 'assignment_id': ids['asg'],
        'class_subject_id': ids['cs'], 'student_id': ids['student']})
    assert r.status_code == 200
    body = r.get_json()
    names = {row['name'] for row in body['rows']}
    assert {'SSE-CA1', 'SSE-CA2', 'SSE-Exam'} <= names
    # every row starts blank
    assert all(row['score'] == '' for row in body['rows'])


def test_save_student_scores_persists_all(app):
    ids = _setup(app)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with app.app_context():
        ats = {at.name: at.id for at in AssessmentType.query.filter(
            AssessmentType.name.in_(['SSE-CA1', 'SSE-CA2', 'SSE-Exam'])).all()}
    r = c.post('/subjects/scores/save-student', data={
        'term_id': ids['term'], 'assignment_id': ids['asg'], 'class_subject_id': ids['cs'],
        'student_id': ids['student'],
        'assessment_type_id[]': [str(ats['SSE-CA1']), str(ats['SSE-CA2']), str(ats['SSE-Exam'])],
        'score[]': ['15', '18', '55'],
        '_csrf_token': auth_csrf(c)})
    assert r.status_code in (200, 302, 303)
    with app.app_context():
        saved = {s.assessment_type_id: s.score for s in StudentScore.query.filter_by(
            student_id=ids['student'], class_subject_id=ids['cs']).all()}
        assert saved.get(ats['SSE-CA1']) == 15
        assert saved.get(ats['SSE-CA2']) == 18
        assert saved.get(ats['SSE-Exam']) == 55
