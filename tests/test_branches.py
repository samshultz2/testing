"""Stage 1 multi-branch tests: model, default seed, backfill, user scope."""
import re

from config import Config
from models import db, Branch, Student, User
from tests.conftest import login_token


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def _page_token(client):
    html = client.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def test_default_branch_seeded(app):
    with app.app_context():
        default = Branch.get_default()
        assert default is not None
        assert default.is_default is True


def test_existing_data_backfilled_to_default(app):
    """A student created without a branch is backfilled by the seeder."""
    with app.app_context():
        s = Student(student_id='STUBR1', first_name='Br', surname='Anch',
                    gender='Male', is_active=True)
        db.session.add(s)
        db.session.commit()
        assert s.branch_id is None
        from models.models import _seed_branches
        _seed_branches()
        db.session.refresh(s)
        assert s.branch_id == Branch.get_default().id


def test_admin_is_central(app):
    """Legacy/admin accounts default to central scope after seeding."""
    with app.app_context():
        # Create an admin user row, then run the seeder.
        u = User(username='adminx', role='admin', full_name='Admin X')
        u.set_password('secret123')
        db.session.add(u)
        db.session.commit()
        from models.models import _seed_branches
        _seed_branches()
        db.session.refresh(u)
        assert u.scope == 'central'
        assert u.is_central is True


def test_branches_page_and_add(app):
    client = _admin(app)
    assert client.get('/settings/branches').status_code == 200
    token = _page_token(client)
    client.post('/settings/branches/add',
                data={'name': 'Ikeja', 'code': 'IKJ', '_csrf_token': token},
                follow_redirects=True)
    with app.app_context():
        assert Branch.query.filter_by(name='Ikeja').first() is not None


def test_create_branch_scoped_user(app):
    client = _admin(app)
    token = _page_token(client)
    with app.app_context():
        bid = Branch.get_default().id
    client.post('/users/add',
                data={'username': 'branchuser', 'password': 'Secret123',
                      'confirm_password': 'Secret123', 'role': 'staff',
                      'scope': 'branch', 'branch_id': bid, 'modules': 'students',
                      '_csrf_token': token},
                follow_redirects=True)
    with app.app_context():
        u = User.query.filter_by(username='branchuser').first()
        assert u is not None
        assert u.scope == 'branch'
        assert u.branch_id == bid
        assert u.is_central is False
