#!/usr/bin/env python3
"""Daily billing job (multi-tenancy): reminders + purge.

Run once a day. It:
  1. emails each school the reminder due for its lifecycle stage (trial ending,
     renewal in a week / tomorrow, locked-out, final purge warning) — once each,
  2. purges schools that have stayed unpaid past the grace period (database +
     subdomain), by delegating to the reaper.

    python scripts/billing_cron.py             # send reminders + purge
    python scripts/billing_cron.py --dry-run   # report only, send/delete nothing
    python scripts/billing_cron.py --no-purge  # reminders only

Reads CONTROL_PLANE_DATABASE_URL and the SMTP / TENANT_* settings from the env.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import tenancy, billing_notify, autorenew   # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description='Daily billing: auto-renew + reminders + purge.')
    ap.add_argument('--dry-run', action='store_true', help='Report only; charge/send/delete nothing.')
    ap.add_argument('--no-purge', action='store_true', help='Skip purging (still renews + reminds).')
    args = ap.parse_args(argv)
    tenancy.init_control_plane()

    # 1. auto-renew saved cards that are due (before reminders, so a successful
    #    renewal suppresses the "renew now" email).
    renewed = autorenew.charge_due(charge=not args.dry_run)
    if renewed:
        for r in renewed:
            print(f'auto-renew: {r["subdomain"]} [{r["action"]}]'
                  + (f' — {r.get("reason")}' if r.get('reason') else ''))
    else:
        print('No cards due for auto-renew.')

    sent = billing_notify.run_notifications(send=not args.dry_run)
    if sent:
        for sub, marker in sent:
            print(f'{"would notify" if args.dry_run else "notified"}: {sub} [{marker}]')
    else:
        print('No reminders due.')

    if not args.no_purge:
        from scripts.reap_unpaid_tenants import main as reap
        print('\n-- purge --')
        reap(['--dry-run'] if args.dry_run else [])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
