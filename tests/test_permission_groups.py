"""Permission groups: group is the base, per-user overrides win."""
from models import db, User, PermissionGroup
from config import Config
from tests.conftest import login_token, auth_csrf


def test_group_provides_base_permissions(app):
    with app.app_context():
        g = PermissionGroup(name='Form Teachers')
        g.set_permissions({'students': 'view', 'results': 'edit', 'attendance': 'edit'})
        u = User(username='pg_base', role='teacher')
        u.permission_group = g
        assert u.permission_map == {'students': 'view', 'results': 'edit',
                                    'attendance': 'edit'}


def test_overrides_win_over_group(app):
    with app.app_context():
        g = PermissionGroup(name='Base2')
        g.set_permissions({'students': 'view', 'results': 'edit', 'attendance': 'edit'})
        u = User(username='pg_ovr', role='teacher')
        u.permission_group = g
        # raise students view->edit, REVOKE attendance, ADD a module the group lacks
        u.set_permissions({'students': 'edit', 'attendance': 'none', 'cbt': 'view'})
        pm = u.permission_map
        assert pm['students'] == 'edit'      # override raised
        assert 'attendance' not in pm        # override revoked a group grant
        assert pm['cbt'] == 'view'           # override added
        assert pm['results'] == 'edit'       # untouched group grant remains


def test_inactive_group_contributes_nothing(app):
    with app.app_context():
        g = PermissionGroup(name='Disabled', is_active=False)
        g.set_permissions({'students': 'edit', 'results': 'edit'})
        u = User(username='pg_off', role='teacher')
        u.permission_group = g
        u.set_permissions({'cbt': 'view'})
        assert u.permission_map == {'cbt': 'view'}   # only the override applies


def test_no_group_falls_back_to_legacy_modules(app):
    import json
    with app.app_context():
        u = User(username='pg_legacy', role='teacher')
        u.allowed_modules = json.dumps(['students', 'results'])
        assert u.permission_map == {'students': 'edit', 'results': 'edit'}


def test_group_crud_and_assignment_http(app):
    """End-to-end: a central admin creates a group and assigns it to a new user."""
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD,
                           '_csrf_token': login_token(c)})
    tok = auth_csrf(c)
    # Create a group with two module grants.
    c.post('/users/groups/add', data={
        '_csrf_token': tok, 'name': 'Librarians',
        'perm_library': 'edit', 'perm_students': 'view',
    }, follow_redirects=True)
    with app.app_context():
        g = PermissionGroup.query.filter_by(name='Librarians').first()
        assert g and g.permission_map == {'library': 'edit', 'students': 'view'}
        gid = g.id
    # Create a user in that group, with a per-user revoke of 'students'.
    c.post('/users/add', data={
        '_csrf_token': tok, 'username': 'lib1', 'full_name': 'Lib One',
        'password': 'StrongPass1!x', 'confirm_password': 'StrongPass1!x',
        'role': 'staff', 'permission_group_id': str(gid),
        'perm_students': 'none',
    }, follow_redirects=True)
    with app.app_context():
        u = User.query.filter_by(username='lib1').first()
        assert u.permission_group_id == gid
        pm = u.permission_map
        assert pm.get('library') == 'edit'   # inherited from group
        assert 'students' not in pm          # per-user revoke won
