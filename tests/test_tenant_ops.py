"""Multi-tenancy Stage 2: run migrations across every school's database."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


def test_migrate_all_tenants_brings_each_to_head(tmp_path, monkeypatch):
    monkeypatch.setenv('CONTROL_PLANE_DATABASE_URL', 'sqlite:///' + str(tmp_path / 'cp.db'))
    monkeypatch.setenv('TENANT_DB_DIR', str(tmp_path / 'tenants'))
    from utils import tenancy, provisioning, tenant_admin
    tenancy._reset_engine()
    tenancy.init_control_plane()
    tenancy.register_tenant('Alpha', 'alpha')
    tenancy.register_tenant('Beta', 'beta')
    provisioning.provision('alpha')
    provisioning.provision('beta')

    head = provisioning._alembic_head()
    # active_tenants finds both; migrate each (idempotent — already at head).
    targets = tenant_admin.active_tenants()
    assert {t.subdomain for t in targets} == {'alpha', 'beta'}
    for t in targets:
        tenant_admin.migrate_tenant(t.database_url)      # must not raise

    for sub in ('alpha', 'beta'):
        t = tenancy.get_tenant(sub)
        eng = create_engine(t.database_url)
        with Session(eng) as s:
            assert s.execute(text('SELECT version_num FROM alembic_version')).scalar() == head
        eng.dispose()
    tenancy._reset_engine()
