"""A form teacher must only reach their own students through search, export,
the JSON stats endpoint and the student detail view — not the whole branch."""
from datetime import date
from flask import session
from models import (db, Branch, User, Teacher, Student, SchoolClass, ClassArm,
                    ClassArmAssignment, StudentEnrollment, TeacherClassAssignment,
                    AcademicSession, Term)
from tests.conftest import login_token, page_token


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


def test_teacher_students_api_scoped(app):
    ids = _seed_teacher_and_students(app)
    c = _login_teacher(app)
    try:
        j = c.get('/api/students?per_page=50').get_json()
        sids = {s['student_id'] for s in j['students']}
        assert 'TVS_MINE' in sids and 'TVS_OTHER' not in sids
        assert 'classes' in j['filters'] and j['can_add'] is False   # teachers don't add
    finally:
        _deactivate(app)


def test_student_view_page_and_api(app):
    ids = _seed_teacher_and_students(app)
    from config import Config
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    try:
        html = c.get(f'/students/{ids["mine_id"]}').get_data(as_text=True)
        assert 'student-view-app' in html and 'student-data' in html
        j = c.get(f'/api/students/{ids["mine_id"]}').get_json()
        assert j['student']['id'] == ids['mine_id']
        for k in ('contacts', 'enrollments', 'waec', 'jamb', 'discipline', 'clinic', 'urls', 'can_manage'):
            assert k in j
    finally:
        _deactivate(app)


def test_teacher_cannot_view_other_student_api(app):
    ids = _seed_teacher_and_students(app)
    c = _login_teacher(app)
    try:
        assert c.get(f'/api/students/{ids["mine_id"]}').status_code == 200
        assert c.get(f'/api/students/{ids["other_id"]}').status_code == 403
    finally:
        _deactivate(app)


def test_add_student_form_payload(auth_client):
    html = auth_client.get('/students/add').get_data(as_text=True)
    assert 'student-form-app' in html and 'student-form-data' in html
    assert '"mode": "add"' in html


def test_add_student_json_create(auth_client, app):
    tok = page_token(auth_client)
    r = auth_client.post('/students/add', headers={'X-Requested-With': 'fetch'}, data={
        'surname': 'QAForm', 'first_name': 'Kid', 'gender': 'Male',
        'contact_name[]': 'Mr QA', 'phone_number[]': '08011112222', 'relationship[]': 'Father',
        'waec_subjects[]': 'Mathematics', '_csrf_token': tok})
    assert r.status_code == 200
    body = r.get_json()
    assert body['ok'] and '/students/' in body['redirect']
    with app.app_context():
        s = Student.query.filter_by(surname='QAForm', first_name='Kid').first()
        assert s is not None and s.parent_contacts.count() == 1
        assert s.waec_subject_list == ['Mathematics']
        s.parent_contacts.delete()
        db.session.delete(s)
        db.session.commit()


def test_edit_student_json_update(auth_client, app):
    ids = _seed_teacher_and_students(app)
    tok = page_token(auth_client)
    r = auth_client.post(f'/students/{ids["mine_id"]}/edit', headers={'X-Requested-With': 'fetch'},
                         data={'form_complete': '1', 'surname': 'Mine', 'first_name': 'Zara',
                               'gender': 'Female', 'hobbies': 'Chess, Coding', '_csrf_token': tok})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        assert db.session.get(Student, ids['mine_id']).hobbies == 'Chess, Coding'
    _deactivate(app)


def test_teacher_cannot_edit_other_student(app):
    ids = _seed_teacher_and_students(app)
    c = _login_teacher(app)
    try:
        assert c.get(f'/students/{ids["other_id"]}/edit').status_code in (302, 303)
        tok = page_token(c)
        r = c.post(f'/students/{ids["other_id"]}/edit', headers={'X-Requested-With': 'fetch'},
                   data={'form_complete': '1', 'surname': 'X', 'first_name': 'Y',
                         'gender': 'Male', '_csrf_token': tok})
        assert r.status_code == 403
    finally:
        _deactivate(app)


def test_students_api_sort_by_age(app):
    """Sorting by age must not 500 (age is a property, mapped to DOB) and must
    put the oldest student first when order=desc."""
    ids = _seed_teacher_and_students(app)
    with app.app_context():
        older = db.session.get(Student, ids['mine_id'])
        younger = db.session.get(Student, ids['other_id'])
        older.date_of_birth = date(2005, 1, 1)
        younger.date_of_birth = date(2012, 1, 1)
        db.session.commit()
    from config import Config
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    try:
        r = c.get('/api/students?sort=age&order=desc')
        assert r.status_code == 200
        order = [s['id'] for s in r.get_json()['students']]
        assert order.index(ids['mine_id']) < order.index(ids['other_id'])
    finally:
        _deactivate(app)


def test_students_api_shape_and_pagination(app):
    from config import Config
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    j = c.get('/api/students?per_page=5&page=1').get_json()
    assert j['per_page'] == 5 and 'page' in j and 'pages' in j and 'total' in j
    assert isinstance(j['students'], list)
    assert set(j['filters']) == {'classes', 'arms', 'religions', 'streams', 'subjects'}
    if j['students']:
        s = j['students'][0]
        assert {'id', 'student_id', 'name', 'gender', 'url'} <= set(s)


def test_trash_is_teacher_scoped(app):
    """A form teacher's trash shows only their own (form-class) deleted students,
    not other classes' — branch + teacher scoped."""
    ids = _seed_teacher_and_students(app)
    with app.app_context():
        for sid in (ids['mine_id'], ids['other_id']):
            db.session.get(Student, sid).is_active = False
        db.session.commit()
    try:
        c = _login_teacher(app)
        html = c.get('/students/trash').get_data(as_text=True)
        assert 'TVS_MINE' in html        # the teacher's own deleted student
        assert 'TVS_OTHER' not in html   # another class's student is hidden
    finally:
        with app.app_context():
            for sid in (ids['mine_id'], ids['other_id']):
                db.session.get(Student, sid).is_active = True
            db.session.commit()
        _deactivate(app)


def _deactivate(app):
    with app.app_context():
        t = Term.query.filter_by(name='TVS-Term').first()
        if t:
            t.is_active = False
            db.session.commit()
