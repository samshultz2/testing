#!/usr/bin/env python3
"""Billing test helpers (multi-tenancy): inspect a school's billing state and
move its dates so you can jump to any point in the lifecycle without waiting.

    python scripts/billing_devtools.py show                 # all schools + state
    python scripts/billing_devtools.py show glovic          # one school
    python scripts/billing_devtools.py trial glovic 1       # trial ends in 1 day
    python scripts/billing_devtools.py trial glovic -1      # trial ended 1 day ago (soft grace)
    python scripts/billing_devtools.py paid  glovic 6       # subscription ends in 6 days (7-day reminder)
    python scripts/billing_devtools.py paid  glovic -3      # locked out 2 days (past soft grace)

Then drive the flow: log in as the school, hit any page (locked schools redirect
to /billing), pay (test mode or a Paystack test card), and re-run `show`.
Reads CONTROL_PLANE_DATABASE_URL. Intended for staging/dev — it edits real dates.
"""
import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import tenancy, billing            # noqa: E402
from utils.billing_notify import due_notice   # noqa: E402


def _state(t):
    if billing.is_owner(t):
        return 'owner (free forever)'
    if billing.is_locked_out(t):
        return 'LOCKED OUT'
    if not billing.is_active(t):
        return 'expired (soft grace — still usable)'
    if billing.on_trial(t):
        return f'trial · {billing.days_left(t)}d left'
    return f'active · {billing.days_left(t)}d left'


def show(sub=None):
    rows = [tenancy.get_tenant(sub)] if sub else tenancy.list_tenants()
    rows = [r for r in rows if r]
    if not rows:
        print('no such school' if sub else 'no schools registered')
        return 1
    for t in rows:
        au = billing.access_until(t)
        notice = due_notice(t) or '-'
        print(f'{t.subdomain:16} {_state(t):40} '
              f'access_until={au.strftime("%Y-%m-%d %H:%M") if au else "-":16} '
              f'reapable={billing.is_reapable(t)!s:5} due_notice={notice}')
    return 0


def set_date(sub, field, days):
    t = tenancy.get_tenant(sub)
    if t is None:
        print(f'no such school: {sub}')
        return 1
    when = dt.datetime.utcnow() + dt.timedelta(days=float(days))
    # Clear the other date so this one alone drives access_until (= max of both),
    # otherwise a still-future trial would keep a "paid -3" school active.
    if field == 'trial':
        kw = {'trial_ends_at': when, 'paid_until': None}
    else:
        kw = {'paid_until': when, 'trial_ends_at': None}
    tenancy.set_billing(sub, plan='standard', **kw)
    tenancy.clear_notice(sub)                 # let reminders re-fire from the new date
    print(f'set {sub} {field}_ends -> {when.strftime("%Y-%m-%d %H:%M")} UTC')
    return show(sub)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('show'); s.add_argument('subdomain', nargs='?')
    for c in ('trial', 'paid'):
        p = sub.add_parser(c); p.add_argument('subdomain'); p.add_argument('days')
    args = ap.parse_args(argv)
    tenancy.init_control_plane()
    if args.cmd == 'show':
        return show(args.subdomain)
    return set_date(args.subdomain, args.cmd, args.days)


if __name__ == '__main__':
    raise SystemExit(main())
