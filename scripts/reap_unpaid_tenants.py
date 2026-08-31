#!/usr/bin/env python3
"""Delete the databases of schools that never paid (multi-tenancy billing).

A standard school gets a free trial, then must pay. If it stays unpaid past the
grace period (TENANT_BILLING_GRACE_DAYS), its database is deleted here and the
registry row is marked. The OWNER school is exempt — it is never touched.

    python scripts/reap_unpaid_tenants.py            # actually delete
    python scripts/reap_unpaid_tenants.py --dry-run  # just report

Run daily from cron / a systemd timer. Reads CONTROL_PLANE_DATABASE_URL.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import tenancy, provisioning, billing   # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description='Delete unpaid, past-grace school databases.')
    ap.add_argument('--dry-run', action='store_true', help='Report without deleting.')
    args = ap.parse_args(argv)
    tenancy.init_control_plane()

    reaped = 0
    for t in tenancy.list_tenants():
        if t.status != 'active':
            continue
        if billing.is_owner(t):
            continue                     # the owner school is never reaped
        if not billing.is_reapable(t):
            continue
        if args.dry_run:
            print(f'would delete: {t.subdomain} (access ended {billing.access_until(t)})')
            continue
        try:
            # Full purge: drop the database AND remove the registry row, so the
            # subdomain is released too — nothing of the school remains.
            provisioning.drop_tenant(t.subdomain, forget=True)
            print(f'✓ purged {t.subdomain} (database + subdomain)')
            reaped += 1
        except Exception as e:
            print(f'✗ {t.subdomain}: {e}')
    if not args.dry_run:
        print(f'\nDone: {reaped} school(s) purged (database + subdomain).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
