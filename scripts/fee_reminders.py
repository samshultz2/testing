#!/usr/bin/env python3
"""Prepare a Draft fee-reminder SMS campaign for the active term's defaulters.

Normally the background worker runs this daily when FEE_REMINDER_ENABLED=1. Use
this script to test or trigger it by hand:

    python scripts/fee_reminders.py --dry-run   # report counts, create nothing
    python scripts/fee_reminders.py --force      # create a draft now, ignoring
                                                 # the opt-in flag and interval

The draft is queued for staff to review and send — it is never auto-dispatched.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app  # noqa: E402
from utils.reminders import run_fee_reminders  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dry-run', action='store_true',
                    help='Report how many defaulters would be messaged; create nothing.')
    ap.add_argument('--force', action='store_true',
                    help='Create a draft now, bypassing the opt-in flag and interval guard.')
    args = ap.parse_args()

    app = create_app()
    with app.app_context():
        result = run_fee_reminders(app, dry_run=args.dry_run, force=args.force)
    print(result)


if __name__ == '__main__':
    main()
