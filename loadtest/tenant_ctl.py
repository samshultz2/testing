#!/usr/bin/env python3
"""Create / destroy an EPHEMERAL tenant (subdomain) for load testing, and seed it.

    python loadtest/tenant_ctl.py create  loadtest      # provision + seed -> prints EXAM_ID + URL
    python loadtest/tenant_ctl.py destroy loadtest      # drop the tenant DB + registry row

Safety: both actions refuse any subdomain that doesn't start with LOADTEST_TENANT_PREFIX
(default "loadtest"), so this can never provision over or destroy a real school. Run
on the box with control-plane DB access (it uses the same provisioning path the
platform admin uses). Requires wildcard DNS + TLS for *.<base domain> so the new
subdomain is reachable immediately (which is already how tenant subdomains work).
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

PREFIX = os.environ.get('LOADTEST_TENANT_PREFIX', 'loadtest')
N = int(os.environ.get('N', '1000'))
BANK = int(os.environ.get('BANK', '600'))


def _guard(subdomain):
    sub = (subdomain or '').strip().lower()
    if not sub.startswith(PREFIX):
        sys.exit(f'REFUSING: "{sub}" does not start with the safe prefix '
                 f'"{PREFIX}". This tool only touches ephemeral load-test tenants.')
    return sub


def _base_domain():
    from config import Config
    return (os.environ.get('TENANT_BASE_DOMAIN')
            or getattr(Config, 'TENANT_BASE_DOMAIN', '') or 'edusyncra.site')


def create(subdomain):
    sub = _guard(subdomain)
    from utils import tenancy, provisioning, tenant_admin
    from loadtest.seed_mock_jamb import seed_current_app, write_csv

    t = tenancy.get_tenant(sub)
    if t is None:
        tenancy.register_tenant(name=f'Load Test ({sub})', subdomain=sub)
    t = tenancy.get_tenant(sub)
    if t.status != 'active':
        print(f'==> Provisioning tenant "{sub}" (new physical DB) ...')
        provisioning.provision(sub, admin_username='loadadmin')
        t = tenancy.get_tenant(sub)
    else:
        print(f'==> Tenant "{sub}" already active; reseeding.')

    print(f'==> Seeding {N} students + bank ({BANK}/subject) into {sub} DB ...')
    app = tenant_admin.tenant_app(t.database_url)
    with app.app_context():
        exam_id, rows = seed_current_app(N, BANK)
    path = write_csv(rows)

    url = f'https://{sub}.{_base_domain()}'
    print(f'\nTENANT_URL={url}')
    print(f'EXAM_ID={exam_id}')
    print(f'credentials -> {path}')


def destroy(subdomain):
    sub = _guard(subdomain)
    from utils import provisioning, tenancy
    if tenancy.get_tenant(sub) is None:
        print(f'==> No tenant "{sub}" to destroy.'); return
    print(f'==> Destroying tenant "{sub}" (dropping its database + registry row) ...')
    provisioning.drop_tenant(sub, forget=True)
    print(f'==> Done. "{sub}" is gone.')


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ('create', 'destroy'):
        sys.exit('usage: python loadtest/tenant_ctl.py {create|destroy} <subdomain>')
    (create if sys.argv[1] == 'create' else destroy)(sys.argv[2])


if __name__ == '__main__':
    main()
