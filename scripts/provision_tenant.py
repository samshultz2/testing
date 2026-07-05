#!/usr/bin/env python3
"""Register and provision a school (tenant) — Stage 1 of multi-tenancy.

Examples:
    # list all schools and their status
    python scripts/provision_tenant.py --list

    # register + provision a new school in one go
    python scripts/provision_tenant.py --name "Pioneer Education" \
        --subdomain pioneer --admin-email head@pioneer.example

    # just record it as pending (provision later)
    python scripts/provision_tenant.py --name "Summit" --subdomain summit --register-only

    # tear a tenant's database down again (dev/testing)
    python scripts/provision_tenant.py --subdomain summit --drop

Control-plane location comes from CONTROL_PLANE_DATABASE_URL; tenant databases
from TENANT_DATABASE_URL_TEMPLATE (Postgres) or TENANT_DB_DIR (SQLite, dev).
"""
import argparse
import os
import sys

# Allow running as a plain script from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import tenancy, provisioning   # noqa: E402


def _print_tenants():
    rows = tenancy.list_tenants()
    if not rows:
        print('No schools registered yet.')
        return
    print(f'{"SUBDOMAIN":22} {"STATUS":12} DATABASE')
    for t in rows:
        print(f'{t.subdomain:22} {t.status:12} {t.database_url or "-"}')


def main(argv=None):
    ap = argparse.ArgumentParser(description='Provision a school (tenant) database.')
    ap.add_argument('--list', action='store_true', help='List registered schools and exit.')
    ap.add_argument('--name', help='School display name.')
    ap.add_argument('--subdomain', help='Subdomain / slug (e.g. "pioneer").')
    ap.add_argument('--admin-email', help='Email for the school\'s first admin.')
    ap.add_argument('--password', help='Admin temp password (generated if omitted).')
    ap.add_argument('--register-only', action='store_true',
                    help='Only record the school as pending; do not create its database.')
    ap.add_argument('--drop', action='store_true',
                    help='Tear down the tenant database and reset it to pending.')
    args = ap.parse_args(argv)

    tenancy.init_control_plane()

    if args.list:
        _print_tenants()
        return 0

    if args.drop:
        if not args.subdomain:
            ap.error('--drop requires --subdomain')
        provisioning.drop_tenant(args.subdomain)
        print(f'Dropped database for "{args.subdomain}" (reset to pending).')
        return 0

    if not args.subdomain:
        ap.error('--subdomain is required (or use --list)')

    existing = tenancy.get_tenant(args.subdomain)
    if existing is None:
        if not args.name:
            ap.error('--name is required to register a new school')
        tenancy.register_tenant(args.name, args.subdomain, args.admin_email)
        print(f'Registered "{args.subdomain}" (pending).')

    if args.register_only:
        return 0

    tenant, user, pw = provisioning.provision(args.subdomain, admin_password=args.password)
    print(f'\n✓ Provisioned {tenant.subdomain}')
    print(f'  database:      {tenant.database_url}')
    print(f'  admin login:   {user}')
    print(f'  temp password: {pw}')
    print('  (the admin must change this password on first login)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
