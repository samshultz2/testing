"""Phase 2 granularity: the Students and Attendance modules are now sliced into
sub-sections that can be granted/revoked independently.

Students : roster | manage | bulk | delete | idcards | welfare
Attendance: mark | reports | interventions | notify

A user granted a single slice can use only that slice; a user granted the whole
module still passes every slice (backward compatible); admins are unaffected.
"""
import re

from config import Config
from models import db, User, Student, DisciplineRecord
from utils.access_control import MODULE_SUBSECTIONS, subsection_for_endpoint
from tests.conftest import login_token


def _make_user(app, username, perms):
    """Create a staff user with an explicit permission map (module or module.sub)."""
    with app.app_context():
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, role='staff', full_name=username.title())
            u.set_password('secret123')
            db.session.add(u)
        u.set_permissions(perms)
        db.session.commit()


def _login(app, username, password='secret123'):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'username': username, 'password': password,
                                '_csrf_token': token})
    return client


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD,
                                '_csrf_token': token})
    return client


def _csrf(client):
    html = client.get('/').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def _a_student(app, sid='GRN001'):
    with app.app_context():
        s = Student.query.filter_by(student_id=sid).first()
        if not s:
            s = Student(student_id=sid, first_name='Gran', surname='Ular', gender='Male')
            db.session.add(s)
            db.session.commit()
        return s.id


# --- catalog ---------------------------------------------------------------
def test_subsections_registered():
    assert set(MODULE_SUBSECTIONS['students']) == {
        'roster', 'manage', 'bulk', 'delete', 'idcards', 'welfare'}
    assert set(MODULE_SUBSECTIONS['attendance']) == {
        'mark', 'reports', 'interventions', 'notify'}
    # endpoints resolve, including the welfare blueprint spanning students
    assert subsection_for_endpoint('main.view_student') == ('students', 'roster')
    assert subsection_for_endpoint('main.add_student') == ('students', 'manage')
    assert subsection_for_endpoint('welfare.add_discipline') == ('students', 'welfare')
    assert subsection_for_endpoint('attendance.save_attendance') == ('attendance', 'mark')


# --- students partition ----------------------------------------------------
def test_roster_can_view_but_not_manage(app):
    sid = _a_student(app)
    _make_user(app, 'roster_only', {'students.roster': 'edit'})
    c = _login(app, 'roster_only')
    assert c.get('/students').status_code == 200
    assert c.get(f'/students/{sid}').status_code == 200
    # add form lives in the 'manage' slice -> blocked
    assert c.get('/students/add', follow_redirects=False).status_code in (302, 303)


def test_manage_can_add_but_not_browse(app):
    _make_user(app, 'manage_only', {'students.manage': 'edit'})
    c = _login(app, 'manage_only')
    assert c.get('/students/add').status_code == 200
    assert c.get('/students', follow_redirects=False).status_code in (302, 303)


def test_delete_requires_delete_slice(app):
    sid = _a_student(app, 'GRN002')
    _make_user(app, 'no_delete', {'students.roster': 'edit', 'students.manage': 'edit'})
    c = _login(app, 'no_delete')
    token = _csrf(c)
    resp = c.post(f'/students/{sid}/delete', data={'_csrf_token': token},
                  follow_redirects=False)
    assert resp.status_code in (302, 303)
    with app.app_context():
        assert Student.query.filter_by(id=sid).first() is not None  # untouched


def test_welfare_slice_gates_discipline(app):
    sid = _a_student(app, 'GRN003')
    _make_user(app, 'welfare_only', {'students.welfare': 'edit'})
    _make_user(app, 'roster_no_welfare', {'students.roster': 'edit'})
    with app.app_context():
        before = DisciplineRecord.query.count()

    # welfare slice -> may record discipline
    cw = _login(app, 'welfare_only')
    cw.post(f'/welfare/discipline/{sid}/add',
            data={'description': 'late', '_csrf_token': _csrf(cw)},
            follow_redirects=False)
    with app.app_context():
        after_welfare = DisciplineRecord.query.count()
    assert after_welfare == before + 1

    # roster-only -> blocked
    cr = _login(app, 'roster_no_welfare')
    cr.post(f'/welfare/discipline/{sid}/add',
            data={'description': 'nope', '_csrf_token': _csrf(cr)},
            follow_redirects=False)
    with app.app_context():
        assert DisciplineRecord.query.count() == after_welfare  # no new record


def test_whole_students_module_passes_all_slices(app):
    _make_user(app, 'full_students', {'students': 'edit'})
    c = _login(app, 'full_students')
    assert c.get('/students').status_code == 200
    assert c.get('/students/add').status_code == 200


# --- attendance partition --------------------------------------------------
def test_attendance_mark_vs_reports(app):
    _make_user(app, 'att_mark', {'attendance.mark': 'edit'})
    _make_user(app, 'att_reports', {'attendance.reports': 'edit'})

    cm = _login(app, 'att_mark')
    assert cm.get('/attendance/').status_code == 200
    assert cm.get('/attendance/weekly', follow_redirects=False).status_code in (302, 303)

    cr = _login(app, 'att_reports')
    assert cr.get('/attendance/weekly').status_code == 200
    assert cr.get('/attendance/', follow_redirects=False).status_code in (302, 303)


def test_admin_unaffected(app):
    c = _admin(app)
    assert c.get('/students').status_code == 200
    assert c.get('/students/add').status_code == 200
    assert c.get('/attendance/').status_code == 200
    assert c.get('/attendance/weekly').status_code == 200
