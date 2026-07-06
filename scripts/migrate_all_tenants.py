#!/usr/bin/env python3
"""Run database migrations across every school (Stage 2 of multi-tenancy).

Replaces the single-database `flask db upgrade` when running multi-tenant: it
iterates the tenants registry and upgrades each school's database to the latest
Alembic head. Safe/idempotent — a school already at head is a no-op.

    python scripts/migrate_all_tenants.py            # migrate all active schools
    python scripts/migrate_all_tenants.py --subdomain pioneer   # just one

Reads the registry from CONTROL_PLANE_DATABASE_URL.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import tenancy, tenant_admin   # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description='Migrate all tenant databases to head.')
    ap.add_argument('--subdomain', help='Only migrate this one school.')
    args = ap.parse_args(argv)
    tenancy.init_control_plane()

    if args.subdomain:
        t = tenancy.get_tenant(args.subdomain)
        if not t or t.status != 'active' or not t.database_url:
            print(f'No active school "{args.subdomain}".')
            return 1
        targets = [t]
    else:
        targets = tenant_admin.active_tenants()

    if not targets:
        print('No active schools to migrate.')
        return 0

    failures = 0
    for t in targets:
        try:
            tenant_admin.migrate_tenant(t.database_url)
            print(f'✓ migrated {t.subdomain}')
        except Exception as e:            # keep going; one bad DB shouldn't stop the rest
            failures += 1
            print(f'✗ {t.subdomain}: {e}')
    print(f'\nDone: {len(targets) - failures}/{len(targets)} migrated.')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
