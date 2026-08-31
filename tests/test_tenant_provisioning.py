"""Multi-tenancy Stage 1: the tenants registry + per-school provisioning.

Uses SQLite tenant databases in a temp dir, so it exercises the full flow
(register -> provision -> schema + seed + alembic stamp) and, crucially, that
two schools land in separate, isolated databases."""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


@pytest.fixture()
def cp(tmp_path, monkeypatch):
    """A fresh control plane + tenant dir pointed at a temp location."""
    monkeypatch.setenv('CONTROL_PLANE_DATABASE_URL', 'sqlite:///' + str(tmp_path / 'cp.db'))
    monkeypatch.setenv('TENANT_DB_DIR', str(tmp_path / 'tenants'))
    from utils import tenancy, provisioning
    tenancy._reset_engine()
    tenancy.init_control_plane()
    yield tenancy, provisioning
    tenancy._reset_engine()


def test_register_validates_subdomain(cp):
    tenancy, _ = cp
    with pytest.raises(ValueError):
        tenancy.register_tenant('Bad', 'Not A Subdomain!')
    with pytest.raises(ValueError):
        tenancy.register_tenant('Bad', '-leading-hyphen')
    t = tenancy.register_tenant('Good School', 'good')
    assert t.status == 'pending' and t.subdomain == 'good'
    # no duplicate subdomains
    with pytest.raises(ValueError):
        tenancy.register_tenant('Another', 'good')


def test_provision_two_isolated_tenants(cp):
    tenancy, provisioning = cp
    tenancy.register_tenant('Pioneer Education', 'pioneer', 'head@pioneer.example')
    tenancy.register_tenant('Summit Academy', 'summit', 'head@summit.example')

    t1, u1, p1 = provisioning.provision('pioneer')
    t2, u2, p2 = provisioning.provision('summit')

    assert t1.status == 'active' and t2.status == 'active'
    assert t1.database_url != t2.database_url          # separate databases

    from models import Branch, User
    head = provisioning._alembic_head()
    for t, school in ((t1, 'Pioneer Education'), (t2, 'Summit Academy')):
        eng = create_engine(t.database_url)
        with Session(eng) as s:
            branches = s.query(Branch).all()
            assert len(branches) == 1 and branches[0].is_default   # default branch seeded
            admins = s.query(User).filter_by(role='super_admin').all()
            assert len(admins) == 1                                # one central admin
            assert admins[0].scope == 'central' and admins[0].must_change_password
            # a real school table exists (full schema, not just users/branches)
            assert s.execute(text('SELECT count(*) FROM students')).scalar() == 0
            # stamped at Alembic head so future migrations apply cleanly
            assert s.execute(text('SELECT version_num FROM alembic_version')).scalar() == head
        eng.dispose()

    # Isolation: a write into Pioneer must never be visible in Summit.
    e1 = create_engine(t1.database_url)
    with Session(e1) as s:
        s.add(Branch(name='OnlyInPioneer', is_active=True)); s.commit()
    e1.dispose()
    e2 = create_engine(t2.database_url)
    with Session(e2) as s:
        assert s.query(Branch).filter_by(name='OnlyInPioneer').first() is None
    e2.dispose()

    # Temp admin passwords are strong and distinct.
    from utils.security import is_password_strong
    assert is_password_strong(p1)[0] and is_password_strong(p2)[0]
    assert p1 != p2


def test_reprovision_is_refused_and_drop_resets(cp):
    tenancy, provisioning = cp
    tenancy.register_tenant('Once', 'once')
    provisioning.provision('once')
    # already active -> refuse
    with pytest.raises(ValueError):
        provisioning.provision('once')
    # drop resets to pending so it can be re-provisioned
    provisioning.drop_tenant('once')
    assert tenancy.get_tenant('once').status == 'pending'
    t, _, _ = provisioning.provision('once')
    assert t.status == 'active'


def test_registry_survives_in_control_plane(cp):
    tenancy, provisioning = cp
    tenancy.register_tenant('Alpha', 'alpha')
    tenancy.register_tenant('Beta', 'beta')
    provisioning.provision('alpha')
    subs = {t.subdomain: t.status for t in tenancy.list_tenants()}
    assert subs == {'alpha': 'active', 'beta': 'pending'}
