"""A teacher may enter results only for the subjects they teach in a class —
not other subjects of that class. Admins are unrestricted."""
from models import (db, Branch, User, Teacher, Student, SchoolClass, ClassArm,
                    ClassArmAssignment, StudentEnrollment, Subject, ClassSubject,
                    TeacherSubjectAssignment, AssessmentType, AcademicSession, Term,
                    StudentScore)
from tests.conftest import login_token, page_token


def _goc(model, defaults=None, **kw):
    obj = model.query.filter_by(**kw).first()
    if obj:
        return obj
    obj = model(**kw, **(defaults or {}))
    db.session.add(obj); db.session.flush()
    return obj


def _seed(app):
    with app.app_context():
        bid = Branch.get_default().id
        sess = _goc(AcademicSession, name='RSS-Session')
        term = _goc(Term, session_id=sess.id, term_number=1,
                    defaults={'name': 'RSS-Term', 'is_active': True})
        term.is_active = True
        sc = SchoolClass.query.order_by(SchoolClass.level).first()
        arm = ClassArm.query.first()
        caa = _goc(ClassArmAssignment, class_id=sc.id, arm_id=arm.id, term_id=term.id,
                   defaults={'branch_id': bid})
        subA = _goc(Subject, name='RSS-Maths', defaults={'is_active': True})
        subB = _goc(Subject, name='RSS-English', defaults={'is_active': True})
        csA = _goc(ClassSubject, term_id=term.id, class_id=sc.id, subject_id=subA.id,
                   defaults={'is_active': True})
        csB = _goc(ClassSubject, term_id=term.id, class_id=sc.id, subject_id=subB.id,
                   defaults={'is_active': True})
        at = _goc(AssessmentType, name='RSS-CA', defaults={'max_score': 20, 'is_active': True, 'order': 1})
        stu = _goc(Student, student_id='RSS_STU',
                   defaults={'first_name': 'Re', 'surname': 'Sult', 'gender': 'Male',
                             'is_active': True, 'branch_id': bid})
        _goc(StudentEnrollment, student_id=stu.id, class_arm_assignment_id=caa.id,
             defaults={'is_active': True})
        u = User.query.filter_by(username='rss_teacher').first()
        if not u:
            u = User(username='rss_teacher', role='teacher', scope='branch', branch_id=bid)
            u.set_password('Secret123'); db.session.add(u); db.session.flush()
        t = _goc(Teacher, user_id=u.id, defaults={'employee_id': 'RSS001', 'branch_id': bid})
        t.can_enter_results = True
        # The teacher teaches ONLY subject A in this class.
        _goc(TeacherSubjectAssignment, teacher_id=t.id, class_arm_assignment_id=caa.id,
             subject_id=subA.id, defaults={'is_active': True})
        db.session.commit()
        return {'term': term.id, 'caa': caa.id, 'csA': csA.id, 'csB': csB.id,
                'at': at.id, 'stu': stu.id}


def _login(app, username, password):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'username': username, 'password': password, '_csrf_token': tok})
    return c


def _post_scores(c, ids, cs_id):
    return c.post('/subjects/scores/save', headers={'X-Requested-With': 'fetch'}, data={
        'class_subject_id': cs_id, 'assessment_type_id': ids['at'],
        'assignment_id': ids['caa'], 'term_id': ids['term'],
        'student_id[]': ids['stu'], 'score[]': '15', '_csrf_token': page_token(c)})


def _deactivate(app):
    with app.app_context():
        t = Term.query.filter_by(name='RSS-Term').first()
        if t:
            t.is_active = False
            db.session.commit()


def test_teacher_can_save_own_subject_only(app):
    ids = _seed(app)
    c = _login(app, 'rss_teacher', 'Secret123')
    try:
        # Subject they teach -> saved.
        ok = _post_scores(c, ids, ids['csA'])
        assert ok.status_code == 200 and ok.get_json()['ok']
        with app.app_context():
            assert StudentScore.query.filter_by(student_id=ids['stu'], class_subject_id=ids['csA']).first()

        # Subject they do NOT teach -> rejected, nothing written.
        bad = _post_scores(c, ids, ids['csB'])
        assert bad.status_code == 400 and 'subjects you teach' in bad.get_json()['error']
        with app.app_context():
            assert StudentScore.query.filter_by(student_id=ids['stu'], class_subject_id=ids['csB']).first() is None
    finally:
        _deactivate(app)


def test_admin_can_save_any_subject(app):
    from config import Config
    ids = _seed(app)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    try:
        r = _post_scores(c, ids, ids['csB'])   # a subject no one "teaches"
        assert r.status_code == 200 and r.get_json()['ok']
    finally:
        _deactivate(app)
