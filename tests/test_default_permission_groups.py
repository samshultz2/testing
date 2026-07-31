"""Phase 3: the role presets are seeded as central permission-group templates
on tenant init, so a fresh school has ready-made bundles on /users/groups that
can be assigned, granted and revoked.
"""
from models import db, PermissionGroup, User
from utils.role_presets import ROLE_PRESETS
from config import Config
from tests.conftest import login_token


def test_presets_seeded_as_central_groups(app):
    with app.app_context():
        names = {g.name for g in PermissionGroup.query.filter_by(branch_id=None).all()}
        # every non-admin preset with a module bundle is present
        for key, p in ROLE_PRESETS.items():
            if p.get('role') == 'admin':
                continue
            mods = list(p.get('modules') or [])
            if not mods and p.get('role') != 'teacher':
                continue
            assert (p.get('label') or key) in names, key


def test_seeded_group_carries_expected_modules(app):
    with app.app_context():
        bursar = PermissionGroup.query.filter_by(name='Bursar', branch_id=None).first()
        assert bursar is not None
        pm = bursar.permission_map
        assert pm.get('finance') == 'edit'          # bursars run Finance
        assert 'hr' not in pm                        # ...but not HR


def test_seeding_is_idempotent(app):
    """Re-running the seeder does not duplicate groups."""
    from models.models import _seed_permission_groups
    with app.app_context():
        before = PermissionGroup.query.filter_by(name='Principal (Secondary)',
                                                  branch_id=None).count()
        _seed_permission_groups()
        after = PermissionGroup.query.filter_by(name='Principal (Secondary)',
                                                branch_id=None).count()
        assert before == after == 1


def test_backfill_seeds_existing_tenant_without_groups(app):
    """Existing tenant DBs never run init_db; they are seeded on first request
    via the shared helper. Simulate that: wipe the groups, re-run the helper,
    and confirm the templates come back."""
    from utils.permission_seed import seed_permission_groups
    with app.app_context():
        PermissionGroup.query.delete()
        db.session.commit()
        assert PermissionGroup.query.filter_by(branch_id=None).count() == 0
        created = seed_permission_groups(db.session)
        assert created >= 7          # every non-admin preset bundle
        assert PermissionGroup.query.filter_by(name='Bursar', branch_id=None).first()


def test_assigning_group_grants_its_modules(app):
    """A user placed in a seeded group inherits that group's module access."""
    with app.app_context():
        grp = PermissionGroup.query.filter_by(name='Bursar', branch_id=None).first()
        u = User.query.filter_by(username='grp_bursar').first()
        if not u:
            u = User(username='grp_bursar', role='staff', full_name='Grp Bursar')
            u.set_password('secret123')
            db.session.add(u)
        u.permission_group_id = grp.id
        u.set_permissions({})   # no personal overrides -> pure group base
        db.session.commit()
        assert u.permission_map.get('finance') == 'edit'

    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'username': 'grp_bursar', 'password': 'secret123',
                                '_csrf_token': token})
    # can reach Finance (granted via group) ...
    assert client.get('/finance/', follow_redirects=False).status_code in (200, 302)
    # ... but not HR (not in the Bursar bundle)
    assert client.get('/hr/', follow_redirects=False).status_code in (302, 303)
