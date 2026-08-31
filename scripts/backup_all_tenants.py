#!/usr/bin/env python3
"""Back up every school's database (Stage 2 of multi-tenancy).

Iterates the tenants registry and runs the app's normal daily backup against
each school's database (one pg_dump / SQLite copy per school). Idempotent — the
underlying auto_backup keeps one backup per day per database.

    python scripts/backup_all_tenants.py

Run it from cron / a systemd timer. Reads the registry from
CONTROL_PLANE_DATABASE_URL.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import tenancy, tenant_admin   # noqa: E402


def main():
    tenancy.init_control_plane()
    targets = tenant_admin.active_tenants()
    if not targets:
        print('No active schools to back up.')
        return 0
    failures = 0
    for t in targets:
        try:
            path = tenant_admin.backup_tenant(t.database_url)
            print(f'✓ {t.subdomain}: {path or "already backed up today"}')
        except Exception as e:
            failures += 1
            print(f'✗ {t.subdomain}: {e}')
    print(f'\nDone: {len(targets) - failures}/{len(targets)} backed up.')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
