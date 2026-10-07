"""Sub-section permissions (e.g. Finance: payments but not expenses)."""
import re
from models import db, User, Expense
from tests.conftest import login_token


def _make(app, username, perms):
    with app.app_context():
        if not User.query.filter_by(username=username).first():
            u = User(username=username, role='staff', scope='central', full_name=username)
            u.set_password('secret123'); u.set_permissions(perms)
            db.session.add(u); db.session.commit()


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    return c


def _ptoken(c):
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                  c.get('/').get_data(as_text=True))
    return m.group(1) if m else None


def test_granular_finance_access(app):
    _make(app, 'fpart', {'finance.payments': 'edit', 'finance.expenses': 'view'})
    c = _login(app, 'fpart')
    # granted sub-sections reachable
    assert c.get('/finance/payments').status_code == 200          # payments (edit)
    assert c.get('/finance/expenses').status_code == 200          # expenses (view)
    # ungranted sub-section blocked
    assert c.get('/finance/defaulters', follow_redirects=False).status_code in (302, 303)


def test_view_subsection_blocks_write(app):
    _make(app, 'fpart2', {'finance.payments': 'edit', 'finance.expenses': 'view'})
    c = _login(app, 'fpart2')
    with app.app_context():
        before = Expense.query.count()
    c.post('/finance/expenses/add',
           data={'description': 'Tape', 'amount': 300, '_csrf_token': _ptoken(c)},
           follow_redirects=True)
    with app.app_context():
        assert Expense.query.count() == before        # expenses is view-only -> blocked


def test_subsection_level_helper(app):
    from flask import session
    from utils.access_control import subsection_level, module_level
    _make(app, 'fpart3', {'finance.payments': 'edit'})
    with app.app_context():
        uid = User.query.filter_by(username='fpart3').first().id
    with app.test_request_context('/'):
        session['logged_in'] = True; session['user_id'] = uid
        session['role'] = 'staff'; session['scope'] = 'central'
        assert subsection_level('finance', 'payments') == 'edit'
        assert subsection_level('finance', 'expenses') is None   # not granted
        assert module_level('finance') == 'edit'                 # module visible


def test_results_subsection_scoping(app):
    # WAEC/JAMB live under the 'external_exams' module (blueprint 'results').
    _make(app, 'rwaec', {'external_exams.waec': 'view'})
    c = _login(app, 'rwaec')
    assert c.get('/results/waec').status_code == 200                       # waec granted (view)
    assert c.get('/results/jamb', follow_redirects=False).status_code in (302, 303)  # jamb not granted


# --- admissions partition ---------------------------------------------------
def _an_applicant(app, app_no='TSTADM001'):
    from models import Applicant
    with app.app_context():
        a = Applicant.query.filter_by(application_no=app_no).first()
        if not a:
            a = Applicant(application_no=app_no, first_name='Amara', surname='Okoye', gender='Female')
            db.session.add(a); db.session.commit()
        return a.id


def test_admissions_view_create_but_not_delete_or_convert(app):
    from models import Applicant
    aid = _an_applicant(app, 'TSTADM001')
    _make(app, 'adm_vc', {'admissions.view': 'edit', 'admissions.create': 'edit'})
    c = _login(app, 'adm_vc')
    assert c.get('/admissions/').status_code == 200
    assert c.get('/admissions/applicants').status_code == 200
    assert c.get('/admissions/applicants/add').status_code == 200
    token = _ptoken(c)
    # 'delete' and 'convert' are separate slices -- neither was granted, so
    # both are blocked by the generic subsection gate (redirect -> dashboard,
    # not the applicant-specific error redirect a validation failure would use).
    r = c.post(f'/admissions/applicants/{aid}/delete', data={'_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303) and r.headers['Location'].rstrip('/') == ''
    r2 = c.post(f'/admissions/applicants/{aid}/convert', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303) and r2.headers['Location'].rstrip('/') == ''
    with app.app_context():
        assert db.session.get(Applicant, aid) is not None   # untouched


def test_admissions_delete_slice_allows_delete_but_not_convert(app):
    from models import Applicant
    aid = _an_applicant(app, 'TSTADM002')
    _make(app, 'adm_del', {'admissions.view': 'edit', 'admissions.delete': 'edit'})
    c = _login(app, 'adm_del')
    token = _ptoken(c)
    r = c.post(f'/admissions/applicants/{aid}/convert', data={'_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303) and r.headers['Location'].rstrip('/') == ''
    r2 = c.post(f'/admissions/applicants/{aid}/delete', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303) and r2.headers['Location'].rstrip('/') != ''
    with app.app_context():
        assert db.session.get(Applicant, aid) is None       # delete went through


def test_admissions_download_slice(app):
    _make(app, 'adm_nodl', {'admissions.view': 'edit'})
    c = _login(app, 'adm_nodl')
    r = c.get('/admissions/applicants/blank-form.pdf', follow_redirects=False)
    assert r.status_code in (302, 303)
    _make(app, 'adm_dl', {'admissions.view': 'edit', 'admissions.download': 'edit'})
    c2 = _login(app, 'adm_dl')
    r2 = c2.get('/admissions/applicants/blank-form.pdf')
    assert r2.status_code == 200


# --- the permission_map override-narrowing bug fix --------------------------
def test_group_override_narrows_whole_module_grant(app):
    """A per-user 'none' override on one sub-key (students.purge) must block
    just that slice even when access otherwise comes from a whole-module
    group grant ('students': 'edit') -- not silently no-op because the group
    grant never literally contains the 'students.purge' key to pop."""
    from models import PermissionGroup
    from utils.access_control import MODULE_SUBSECTIONS
    with app.app_context():
        grp = PermissionGroup(name='StudentsFullTest')
        grp.set_permissions({'students': 'edit'})
        db.session.add(grp); db.session.commit()
        u = User.query.filter_by(username='narrow_whole').first()
        if not u:
            u = User(username='narrow_whole', role='staff', full_name='Narrow Whole')
            u.set_password('secret123')
            db.session.add(u)
        u.permission_group_id = grp.id
        u.set_permissions({'students.purge': 'none'})
        db.session.commit()
        pm = u.permission_map
        assert pm.get('students.purge') is None
        for sub in MODULE_SUBSECTIONS['students']:
            if sub == 'purge':
                continue
            assert pm.get(f'students.{sub}') == 'edit'


def test_group_override_narrowing_blocks_endpoint(app):
    """End-to-end: the same whole-module-grant + one-slice-revoked user is
    actually blocked server-side on the revoked slice, not just in the map."""
    from models import PermissionGroup, Student
    with app.app_context():
        grp = PermissionGroup(name='StudentsFullTest2')
        grp.set_permissions({'students': 'edit'})
        db.session.add(grp); db.session.commit()
        u = User.query.filter_by(username='narrow_whole2').first()
        if not u:
            u = User(username='narrow_whole2', role='staff', full_name='Narrow Whole 2')
            u.set_password('secret123')
            db.session.add(u)
        u.permission_group_id = grp.id
        u.set_permissions({'students.purge': 'none'})
        db.session.commit()
        s = Student.query.filter_by(student_id='TSTNRW01').first()
        if not s:
            s = Student(student_id='TSTNRW01', first_name='Nar', surname='Row',
                        gender='Male', is_active=False)
            db.session.add(s); db.session.commit()
        sid = s.id
    c = _login(app, 'narrow_whole2')
    token = _ptoken(c)
    # the module grant still covers everything else -- e.g. restore
    r = c.post(f'/students/{sid}/restore', data={'_csrf_token': token}, follow_redirects=False)
    assert r.status_code in (302, 303, 200)
    with app.app_context():
        Student.query.filter_by(id=sid).update({'is_active': False})
        db.session.commit()
    # but the revoked slice is blocked
    r2 = c.post(f'/students/{sid}/purge', data={'_csrf_token': token}, follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert Student.query.filter_by(id=sid).first() is not None   # not purged


def test_bulk_delete_students_reachable_by_delete_slice(app):
    """bulk_delete_students used to be hard-walled to @admin_required,
    bypassing the granular 'students.delete' grant entirely. It's now
    reachable (and branch/teacher-scoped) like the single delete_student."""
    from models import Student
    with app.app_context():
        s = Student.query.filter_by(student_id='TSTBLK01').first()
        if not s:
            s = Student(student_id='TSTBLK01', first_name='Bulk', surname='One', gender='Male')
            db.session.add(s); db.session.commit()
        sid = s.id
    _make(app, 'bulk_del', {'students.roster': 'edit', 'students.delete': 'edit'})
    c = _login(app, 'bulk_del')
    token = _ptoken(c)
    r = c.post('/students/bulk-delete', data={'student_ids': [str(sid)], '_csrf_token': token})
    assert r.status_code == 200
    assert r.get_json()['deleted'] == 1
    with app.app_context():
        assert Student.query.filter_by(id=sid).first().is_active is False
