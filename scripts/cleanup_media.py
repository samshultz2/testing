#!/usr/bin/env python3
"""Remove stale on-disk media across every school database.

The daily background job already sweeps orphaned communication-attachment files
once per day per school; run this to clear the backlog immediately (or from cron
on a box that doesn't run the in-process jobs). It walks the platform database
plus every registered school and deletes comm-attachment files that have no
``CommAttachment`` row and are older than the grace window.

    python scripts/cleanup_media.py            # 24h grace (safe default)
    python scripts/cleanup_media.py --now      # no grace — delete every orphan now
"""
import sys


def _sweep_bound(label, grace):
    from utils.media_cleanup import sweep_current_tenant
    res = sweep_current_tenant(grace_seconds=grace)
    n, freed = res['comm_deleted'], res['comm_freed']
    print(f'▶ {label}: removed {n} orphaned comm file(s), freed {freed/1024:.0f} KB')
    return n, freed


def main():
    grace = 0 if '--now' in sys.argv else 24 * 3600
    from app import create_app

    total_n, total_freed = 0, 0
    app = create_app()
    with app.app_context():
        n, f = _sweep_bound('platform database', grace)
        total_n += n; total_freed += f

    try:
        from utils import tenancy, tenant_admin
        tenancy.init_control_plane()
        targets = tenant_admin.active_tenants()
    except Exception as exc:
        print(f'(no tenant registry — single-database deploy: {str(exc).splitlines()[0]})')
        targets = []

    for t in targets:
        try:
            tapp = tenant_admin.tenant_app(t.database_url)
            with tapp.app_context():
                n, f = _sweep_bound(f'school: {t.subdomain}', grace)
                total_n += n; total_freed += f
        except Exception as exc:
            print(f'▶ school: {t.subdomain}  ✗ {str(exc).splitlines()[0]}')

    print(f'\nDONE — removed {total_n} file(s), freed {total_freed/1024/1024:.1f} MB total.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
