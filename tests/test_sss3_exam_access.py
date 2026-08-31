"""SSS3 arm teachers get automatic, arm-scoped access to the External Exams
(WAEC/JAMB) module. Removing the assignment revokes it. Branch-scoped.
"""
from config import Config
from models import (db, User, Teacher, TeacherClassAssignment, TeacherSubjectAssignment,
                    Student, StudentEnrollment, SchoolClass, ClassArm, ClassArmAssignment,
                    AcademicSession, Term, Branch, WAECResult, Subject)
from tests.conftest import login_token, auth_csrf


def _get_or_create(model, defaults=None, **kw):
    obj = model.query.filter_by(**kw).first()
    if obj:
        return obj
    obj = model(**kw, **(defaults or {}))
    db.session.add(obj); db.session.flush()
    return obj


def _seed(app, tag, assign='class', class_name='SSS3'):
    """A staff user (no external_exams module) assigned to a `class_name` arm,
    plus a student enrolled in that arm and one in another arm."""
    with app.app_context():
        bid = Branch.get_default().id
        sess = _get_or_create(AcademicSession, name=f'EX-{tag}-S')
        term = _get_or_create(Term, session_id=sess.id, term_number=1,
                              defaults={'name': f'EX-{tag}-T', 'is_active': True})
        term.is_active = True
        cls = _get_or_create(SchoolClass, name=class_name, defaults={'level': 12})
        other_cls = _get_or_create(SchoolClass, name=f'{class_name}-OTHER', defaults={'level': 12})
        arm = _get_or_create(ClassArm, name=f'{tag}A')
        arm2 = _get_or_create(ClassArm, name=f'{tag}B')
        mine = _get_or_create(ClassArmAssignment, class_id=cls.id, arm_id=arm.id,
                              term_id=term.id, defaults={'branch_id': bid})
        other = _get_or_create(ClassArmAssignment, class_id=cls.id, arm_id=arm2.id,
                               term_id=term.id, defaults={'branch_id': bid})
        s_mine = _get_or_create(Student, student_id=f'EX{tag}MINE',
                                defaults={'first_name': 'Ada', 'surname': f'Mine{tag}',
                                          'gender': 'Female', 'is_active': True, 'branch_id': bid})
        s_other = _get_or_create(Student, student_id=f'EX{tag}OTHER',
                                 defaults={'first_name': 'Obi', 'surname': f'Other{tag}',
                                           'gender': 'Male', 'is_active': True, 'branch_id': bid})
        _get_or_create(StudentEnrollment, student_id=s_mine.id,
                       class_arm_assignment_id=mine.id, defaults={'is_active': True})
        _get_or_create(StudentEnrollment, student_id=s_other.id,
                       class_arm_assignment_id=other.id, defaults={'is_active': True})
        u = User.query.filter_by(username=f'exteach_{tag}').first()
        if not u:
            u = User(username=f'exteach_{tag}', role='staff', scope='branch', branch_id=bid)
            u.set_password('Secret123'); db.session.add(u); db.session.flush()
        u.role = 'staff'; u.set_permissions({})           # no external_exams module
        t = _get_or_create(Teacher, user_id=u.id, defaults={'employee_id': f'EX{tag}', 'branch_id': bid})
        if assign == 'class':
            _get_or_create(TeacherClassAssignment, teacher_id=t.id,
                           class_arm_assignment_id=mine.id, defaults={'is_form_teacher': True})
        elif assign == 'subject':
            subj = _get_or_create(Subject, name=f'Sub{tag}', defaults={'is_active': True})
            _get_or_create(TeacherSubjectAssignment, teacher_id=t.id,
                           class_arm_assignment_id=mine.id, subject_id=subj.id,
                           defaults={'is_active': True})
        # Give both students a WAEC result so the list has content.
        for s in (s_mine, s_other):
            _get_or_create(WAECResult, student_id=s.id, exam_year=2025, subject='Mathematics',
                           defaults={'grade': 'B2'})
        db.session.commit()
        return {'uid': u.id, 'tid': t.id, 'mine_caa': mine.id,
                's_mine': s_mine.id, 's_other': s_other.id}


def _login(app, tag):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'username': f'exteach_{tag}', 'password': 'Secret123', '_csrf_token': tok})
    return c


def test_sss3_class_teacher_gets_scoped_access(app):
    ids = _seed(app, 'CLS', assign='class')
    c = _login(app, 'CLS')
    r = c.get('/results/waec?year=2025')     # this test seeds 2025 results
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'MineCLS' in body                 # their own arm's student
    assert 'OtherCLS' not in body            # not the other arm's student


def test_sss3_subject_teacher_also_gets_access(app):
    _seed(app, 'SUB', assign='subject')
    c = _login(app, 'SUB')
    assert c.get('/results/waec').status_code == 200
    assert c.get('/results/jamb').status_code == 200


def test_view_other_arm_student_is_forbidden(app):
    ids = _seed(app, 'IDOR', assign='class')
    c = _login(app, 'IDOR')
    assert c.get(f"/results/waec/student/{ids['s_mine']}").status_code == 200
    assert c.get(f"/results/waec/student/{ids['s_other']}").status_code == 403


def test_access_revoked_when_assignment_removed(app):
    ids = _seed(app, 'REVOKE', assign='class')
    c = _login(app, 'REVOKE')
    assert c.get('/results/waec').status_code == 200
    with app.app_context():
        TeacherClassAssignment.query.filter_by(teacher_id=ids['tid']).update({'is_active': False})
        db.session.commit()
    # Module access is derived from the live assignment — now gone.
    r = c.get('/results/waec')
    assert r.status_code in (302, 403)


def test_non_sss3_assignment_grants_nothing(app):
    _seed(app, 'JSS', assign='class', class_name='JSS1')
    c = _login(app, 'JSS')
    r = c.get('/results/waec')
    assert r.status_code in (302, 403)


def test_derived_teacher_blocked_from_analytics(app):
    _seed(app, 'NOAN', assign='class')
    c = _login(app, 'NOAN')
    # School-wide analytics stays admin/full-module only.
    assert c.get('/results/waec/analytics').status_code in (302, 403)


def test_sss3_teacher_reaches_mock_dashboards(app):
    _seed(app, 'MOCK', assign='class')
    c = _login(app, 'MOCK')
    assert c.get('/mock-jamb/').status_code == 200
    assert c.get('/mock-waec/').status_code == 200


def test_derived_teacher_blocked_from_mock_bank_and_analytics(app):
    _seed(app, 'MOCKX', assign='class')
    c = _login(app, 'MOCKX')
    # Shared question bank and cohort analytics stay admin/full-module only.
    assert c.get('/mock-jamb/bank').status_code in (302, 403)
    assert c.get('/mock-jamb/analytics').status_code in (302, 403)


def test_mock_jamb_student_progress_arm_scoped(app):
    ids = _seed(app, 'MOCKPS', assign='class')
    c = _login(app, 'MOCKPS')
    assert c.get(f"/mock-jamb/student/{ids['s_mine']}").status_code == 200
    assert c.get(f"/mock-jamb/student/{ids['s_other']}").status_code == 403
