"""A form teacher must only reach their own students through search, export,
the JSON stats endpoint and the student detail view — not the whole branch."""
from datetime import date
from flask import session
from models import (db, Branch, User, Teacher, Student, SchoolClass, ClassArm,
                    ClassArmAssignment, StudentEnrollment, TeacherClassAssignment,
                    AcademicSession, Term)
from tests.conftest import login_token


def _get_or_create(model, defaults=None, **kw):
    obj = model.query.filter_by(**kw).first()
    if obj:
        return obj
    obj = model(**kw, **(defaults or {}))
    db.session.add(obj); db.session.flush()
    return obj


def _seed_teacher_and_students(app):
    """Idempotent seed (shared session-scoped DB): a teacher who is form
    teacher of one class, with a student there and one in another class."""
    with app.app_context():
        bid = Branch.get_default().id
        sess = _get_or_create(AcademicSession, name='TVS-Session')
        term = _get_or_create(Term, session_id=sess.id, term_number=1,
                              defaults={'name': 'TVS-Term', 'is_active': True})
        term.is_active = True
        classes = SchoolClass.query.order_by(SchoolClass.level).all()
        arm = ClassArm.query.first()
        mine = _get_or_create(ClassArmAssignment, class_id=classes[0].id, arm_id=arm.id,
                              term_id=term.id, defaults={'branch_id': bid})
        other = _get_or_create(ClassArmAssignment, class_id=classes[1].id, arm_id=arm.id,
                               term_id=term.id, defaults={'branch_id': bid})
        s_mine = _get_or_create(Student, student_id='TVS_MINE',
                                defaults={'first_name': 'Zara', 'surname': 'Mine',
                                          'gender': 'Female', 'is_active': True, 'branch_id': bid})
        s_other = _get_or_create(Student, student_id='TVS_OTHER',
                                 defaults={'first_name': 'Zane', 'surname': 'Other',
                                           'gender': 'Male', 'is_active': True, 'branch_id': bid})
        _get_or_create(StudentEnrollment, student_id=s_mine.id,
                       class_arm_assignment_id=mine.id, defaults={'is_active': True})
        _get_or_create(StudentEnrollment, student_id=s_other.id,
                       class_arm_assignment_id=other.id, defaults={'is_active': True})
        u = User.query.filter_by(username='tvs_teacher').first()
        if not u:
            u = User(username='tvs_teacher', role='teacher', scope='branch', branch_id=bid)
            u.set_password('Secret123'); db.session.add(u); db.session.flush()
        t = _get_or_create(Teacher, user_id=u.id, defaults={'employee_id': 'TVS001', 'branch_id': bid})
        _get_or_create(TeacherClassAssignment, teacher_id=t.id,
                       class_arm_assignment_id=mine.id, defaults={'is_form_teacher': True})
        db.session.commit()
        return {'mine_id': s_mine.id, 'other_id': s_other.id, 'term': term.id}


def _login_teacher(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'username': 'tvs_teacher', 'password': 'Secret123', '_csrf_token': tok})
    return c


def test_teacher_search_only_own_students(app):
    ids = _seed_teacher_and_students(app)
    c = _login_teacher(app)
    try:
        results = c.get('/api/students/search?q=Za').get_json()   # matches both Zara & Zane
        sids = {r['student_id'] for r in results}
        assert 'TVS_MINE' in sids and 'TVS_OTHER' not in sids
    finally:
        _deactivate(app)


def test_teacher_cannot_view_other_students(app):
    ids = _seed_teacher_and_students(app)
    c = _login_teacher(app)
    try:
        assert c.get(f'/students/{ids["mine_id"]}').status_code == 200
        # other class's student → redirected away (not 200 detail)
        assert c.get(f'/students/{ids["other_id"]}').status_code in (302, 303)
    finally:
        _deactivate(app)


def test_teacher_stats_scoped(app):
    ids = _seed_teacher_and_students(app)
    c = _login_teacher(app)
    try:
        j = c.get('/api/dashboard/stats').get_json()
        assert j['total_students'] == 1          # only their student
    finally:
        _deactivate(app)


def _deactivate(app):
    with app.app_context():
        t = Term.query.filter_by(name='TVS-Term').first()
        if t:
            t.is_active = False
            db.session.commit()
