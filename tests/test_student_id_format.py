"""Configurable student-ID format: a school sets a prefix + minimum digit width,
and auto-generated ids follow it (defaulting to STU#####). Also covers per-branch
prefixes (a branch's own Code overrides the school-wide default) and the optional
academic-session code inserted after the prefix."""
from models import db, Student, Branch
from models.models import SchoolSettings
from models.models.academics import AcademicSession
from models.models.student import _session_short_code


def test_default_format(app):
    with app.app_context():
        sid = Student.generate_student_id()
        assert sid.startswith('STU') and sid[3:].isdigit() and len(sid[3:]) == 5


def test_custom_prefix_and_width(app):
    with app.app_context():
        SchoolSettings.set('student_id_prefix', 'PIO', 'string')
        SchoolSettings.set('student_id_digits', 6, 'int')
        assert Student.student_id_format() == ('PIO', 6)
        s = Student(student_id='PIO000042', first_name='A', surname='B',
                    gender='Male', is_active=True)
        db.session.add(s); db.session.commit()
        try:
            nxt = Student.generate_student_id()
            assert nxt == 'PIO000043'                 # continues the running number
        finally:
            db.session.delete(s)
            SchoolSettings.set('student_id_prefix', 'STU', 'string')
            SchoolSettings.set('student_id_digits', 5, 'int')
            db.session.commit()


def test_academic_settings_saves_format(app):
    from config import Config
    from tests.conftest import login_token, auth_csrf
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    csrf = auth_csrf(c)
    r = c.post('/settings/academic', data={
        'student_id_prefix': 'abc', 'student_id_digits': '7', '_csrf_token': csrf},
        headers={'X-Requested-With': 'fetch'})
    assert r.status_code in (200, 302)
    with app.app_context():
        assert SchoolSettings.get('student_id_prefix') == 'ABC'   # upper-cased
        assert SchoolSettings.get('student_id_digits') == 7
        # restore
        SchoolSettings.set('student_id_prefix', 'STU', 'string')
        SchoolSettings.set('student_id_digits', 5, 'int')
        db.session.commit()


def test_academic_settings_saves_include_session_toggle(app):
    from config import Config
    from tests.conftest import login_token, auth_csrf
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    csrf = auth_csrf(c)
    r = c.post('/settings/academic', data={
        'student_id_include_session': '1', '_csrf_token': csrf},
        headers={'X-Requested-With': 'fetch'})
    assert r.status_code in (200, 302)
    with app.app_context():
        assert SchoolSettings.get('student_id_include_session') is True
        SchoolSettings.set('student_id_include_session', False, 'bool')
        db.session.commit()


def test_session_short_code_parses_yyyy_yyyy():
    assert _session_short_code('2025/2026') == '2526'
    assert _session_short_code('2026/2027') == '2627'


def test_session_short_code_rejects_other_shapes():
    assert _session_short_code('') is None
    assert _session_short_code(None) is None
    assert _session_short_code('2025-2026') is None
    assert _session_short_code('Session 1') is None


def test_branch_with_code_overrides_global_prefix(app):
    with app.app_context():
        b = Branch(name='ZzIdNewBenin', code='NB')
        db.session.add(b); db.session.commit()
        try:
            assert Student.student_id_format(b.id) == ('NB', 5)
            sid = Student.generate_student_id(b.id)
            assert sid.startswith('NB') and sid[2:].isdigit()
        finally:
            db.session.delete(b); db.session.commit()


def test_branch_without_code_falls_back_to_global_prefix(app):
    with app.app_context():
        b = Branch(name='ZzIdNoCodeBranch', code=None)
        db.session.add(b); db.session.commit()
        try:
            assert Student.student_id_format(b.id) == ('STU', 5)
        finally:
            db.session.delete(b); db.session.commit()


def test_two_branches_get_independent_id_sequences(app):
    with app.app_context():
        nb = Branch(name='ZzIdNewBenin2', code='NB2')
        jm = Branch(name='ZzIdJemila2', code='JM2')
        db.session.add_all([nb, jm]); db.session.commit()
        try:
            sid_nb = Student.generate_student_id(nb.id)
            sid_jm = Student.generate_student_id(jm.id)
            assert sid_nb.startswith('NB2')
            assert sid_jm.startswith('JM2')
            s1 = Student(student_id=sid_nb, first_name='A', surname='B', gender='Male',
                        is_active=True, branch_id=nb.id)
            db.session.add(s1); db.session.commit()
            # Jemila's next id is unaffected by New Benin having just taken one.
            assert Student.generate_student_id(jm.id) == sid_jm
            db.session.delete(s1); db.session.commit()
        finally:
            db.session.delete(nb); db.session.delete(jm); db.session.commit()


def test_include_session_inserts_code_after_prefix(app):
    with app.app_context():
        AcademicSession.query.update({AcademicSession.is_active: False})
        sess = AcademicSession(name='2025/2026', is_active=True)
        db.session.add(sess); db.session.commit()
        SchoolSettings.set('student_id_include_session', True, 'bool')
        db.session.commit()
        try:
            assert Student.student_id_format() == ('STU2526', 5)
            sid = Student.generate_student_id()
            assert sid.startswith('STU2526')
        finally:
            SchoolSettings.set('student_id_include_session', False, 'bool')
            db.session.delete(sess); db.session.commit()


def test_include_session_combines_with_branch_prefix(app):
    with app.app_context():
        AcademicSession.query.update({AcademicSession.is_active: False})
        sess = AcademicSession(name='2026/2027', is_active=True)
        b = Branch(name='ZzIdJemila3', code='JM3')
        db.session.add_all([sess, b]); db.session.commit()
        SchoolSettings.set('student_id_include_session', True, 'bool')
        db.session.commit()
        try:
            assert Student.student_id_format(b.id) == ('JM32627', 5)
        finally:
            SchoolSettings.set('student_id_include_session', False, 'bool')
            db.session.delete(sess); db.session.delete(b); db.session.commit()


def test_add_student_route_uses_the_chosen_branchs_prefix(app):
    """End-to-end: POSTing /students/add for a branch with its own Code gets
    an id in THAT prefix, not the school-wide default."""
    import re as _re
    from config import Config
    from tests.conftest import login_token

    with app.app_context():
        b = Branch(name='ZzIdRouteBranch', code='RB')
        db.session.add(b); db.session.commit()
        bid = b.id

    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    html = c.get('/students/add').get_data(as_text=True)
    m = _re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    token = m.group(1) if m else None
    c.post('/students/add', data={
        'first_name': 'ZzRouteBranch', 'surname': 'Test', 'gender': 'Male',
        'branch_id': bid, '_csrf_token': token,
    }, follow_redirects=True)

    with app.app_context():
        s = Student.query.filter_by(first_name='ZzRouteBranch', surname='Test').first()
        assert s is not None
        assert s.branch_id == bid
        assert s.student_id.startswith('RB')
        db.session.delete(s)
        db.session.delete(db.session.get(Branch, bid))
        db.session.commit()


def test_bulk_import_uses_the_targeted_branchs_prefix(app):
    from utils.excel_utils import import_student_rows
    from models import ParentContact

    with app.app_context():
        b = Branch(name='ZzIdImportBranch', code='IB')
        db.session.add(b); db.session.commit()
        bid = b.id
        rows = [('Surname', 'First Name', 'Gender'), ('ImportTest', 'ZzIdImport', 'Male')]
        created, _messages = import_student_rows(rows, db, Student, ParentContact, branch_id=bid)
        assert created == 1
        s = Student.query.filter_by(first_name='ZzIdImport', surname='ImportTest').first()
        assert s is not None
        assert s.branch_id == bid
        assert s.student_id.startswith('IB')
        db.session.delete(s)
        db.session.delete(db.session.get(Branch, bid))
        db.session.commit()


def test_admission_conversion_uses_the_applicants_branchs_prefix(app):
    from utils.admissions import convert_to_student
    from models.models_admissions import Applicant

    with app.app_context():
        b = Branch(name='ZzIdApplicantBranch', code='AB')
        db.session.add(b); db.session.commit()
        bid = b.id
        applicant = Applicant(first_name='ZzIdApplicant', surname='Convert', gender='Female',
                              branch_id=bid, application_no='ZZIDAPP1')
        db.session.add(applicant); db.session.commit()
        try:
            student, err = convert_to_student(applicant)
            assert err is None
            assert student.branch_id == bid
            assert student.student_id.startswith('AB')
        finally:
            db.session.delete(applicant)
            s = Student.query.filter_by(first_name='ZzIdApplicant', surname='Convert').first()
            if s:
                db.session.delete(s)
            db.session.delete(db.session.get(Branch, bid))
            db.session.commit()


def test_new_session_restarts_numbering_for_same_branch(app):
    """A student issued under one session's code doesn't block the next id in
    a DIFFERENT session's code from starting back at 1 -- the numbering is
    scoped to the full (branch prefix + session code) string. Uses a
    dedicated branch code (not the bare global 'STU' prefix) so this can't
    collide with ids any other test in the shared, session-scoped test DB
    happens to have left behind under the plain 'STU' namespace."""
    with app.app_context():
        b = Branch(name='ZzIdSessionRestart', code='SR')
        AcademicSession.query.update({AcademicSession.is_active: False})
        old_sess = AcademicSession(name='2024/2025', is_active=True)
        db.session.add_all([b, old_sess]); db.session.commit()
        SchoolSettings.set('student_id_include_session', True, 'bool')
        db.session.commit()
        old_id = Student.generate_student_id(b.id)
        assert old_id == 'SR2425' + '1'.rjust(5, '0')
        s = Student(student_id=old_id, first_name='A', surname='B', gender='Male',
                   is_active=True, branch_id=b.id)
        db.session.add(s); db.session.commit()

        old_sess.is_active = False
        new_sess = AcademicSession(name='2025/2026', is_active=True)
        db.session.add(new_sess); db.session.commit()
        try:
            new_id = Student.generate_student_id(b.id)
            assert new_id == 'SR2526' + '1'.rjust(5, '0')   # fresh sequence, not '2'
        finally:
            SchoolSettings.set('student_id_include_session', False, 'bool')
            db.session.delete(s); db.session.delete(old_sess); db.session.delete(new_sess)
            db.session.delete(b)
            db.session.commit()
