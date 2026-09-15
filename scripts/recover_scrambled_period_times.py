#!/usr/bin/env python3
"""One-time recovery for TimetableSlot rows whose clock times were scrambled
by a now-fixed bug (see utils/timetable_slots.py history): an earlier version
of repair_slot_schedule() rewrote every teaching period's start/end time by
chaining periods back-to-back in `slot_number` order instead of their real
sequence — silently reordering any school whose slot_number didn't exactly
match the periods' intended order (e.g. "Period 5, 7, 1, 2, 3, ...").

That bug is fixed in code, but a fix going forward does not undo times
already written to a database it already ran against. This script rebuilds
the correct sequence from each teaching period's own NAME (e.g. "Period 7"),
which the bug never touched, using each row's own `duration_minutes` (also
never touched by the bug — only start_time/end_time were rewritten), then
re-places every break using its already-correct `after_period`.

Safety:
  - Only proceeds if every active teaching-period name matches "...N" (a
    trailing integer) with no duplicate or missing numbers in 1..count —
    anything else aborts with an explanation rather than guessing.
  - Dry-run by default: prints a full before/after diff and writes nothing.
    Pass --apply to actually commit.
  - Never touches ClassTimetable (subject assignments) or anything besides
    TimetableSlot.start_time/end_time — slot IDs, names and durations are
    preserved exactly, so every class's existing schedule stays linked.

Usage:
    python scripts/recover_scrambled_period_times.py                     # dry run, current DATABASE_URL
    python scripts/recover_scrambled_period_times.py --apply             # apply it
    python scripts/recover_scrambled_period_times.py --subdomain pioneer # target one tenant (multi-tenant setups)
    python scripts/recover_scrambled_period_times.py --start 08:00       # override the day-start anchor
"""
import argparse
import os
import re
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_NAME_NUM = re.compile(r'(\d+)\s*$')


def _plan(teaching, breaks, start_override=None):
    """Compute the corrected (start_time, end_time) for every teaching period
    and break, without writing anything. Returns (plan, error) where plan is
    a list of (slot, new_start, new_end) and error is a string or None."""
    numbered = []
    for t in teaching:
        m = _NAME_NUM.search(t.name or '')
        if not m:
            return None, (f'Teaching slot {t.id} ("{t.name}") has no trailing number — '
                          'cannot safely infer its true position. Aborting; fix names '
                          'manually via Settings -> Timetable Slots instead.')
        numbered.append((int(m.group(1)), t))

    nums = sorted(n for n, _ in numbered)
    expected = list(range(1, len(numbered) + 1))
    if nums != expected:
        return None, (f'Teaching period numbers are {nums}, expected exactly {expected} '
                      '(no gaps or duplicates) — cannot safely reorder. Aborting.')

    numbered.sort(key=lambda p: p[0])
    ordered_teaching = [t for _, t in numbered]

    if start_override:
        h, m = map(int, start_override.split(':'))
        anchor = datetime(2000, 1, 1, h, m)
    else:
        from models import SchoolSettings
        raw = (SchoolSettings.get('school_day_start', '') or '').strip()
        h, m = (8, 20)
        if ':' in raw:
            try:
                h, m = map(int, raw.split(':')[:2])
            except ValueError:
                pass
        anchor = datetime(2000, 1, 1, h, m)

    def duration(slot, default_minutes):
        if slot.duration_minutes:
            return timedelta(minutes=slot.duration_minutes)
        if slot.start_time and slot.end_time:
            d = (datetime.combine(datetime.today(), slot.end_time)
                 - datetime.combine(datetime.today(), slot.start_time))
            if d.total_seconds() > 0:
                return d
        return timedelta(minutes=default_minutes)

    by_after = {}
    for b in breaks:
        if b.after_period is None:
            continue
        n = max(1, min(b.after_period, len(ordered_teaching)))
        by_after.setdefault(n, []).append(b)
    skipped_breaks = [b for b in breaks if b.after_period is None]

    # Single sequential walk through periods AND breaks together, so a break
    # actually pushes every later period's time back by its own duration
    # instead of periods and breaks silently overlapping.
    plan = []
    cursor = anchor
    for i, t in enumerate(ordered_teaching, start=1):
        end = cursor + duration(t, 40)
        plan.append((t, cursor.time(), end.time()))
        cursor = end
        for b in by_after.get(i, []):
            bend = cursor + duration(b, 30)
            plan.append((b, cursor.time(), bend.time()))
            cursor = bend

    # Defensive backstop: a break left untouched (no after_period) could still
    # land inside a newly-repositioned period's time. Surface that rather than
    # silently applying a plan with a new overlap.
    def _mins(t):
        return t.hour * 60 + t.minute
    overlap_msgs = []
    for b in skipped_breaks:
        if not (b.start_time and b.end_time):
            continue
        for slot, ns, ne in plan:
            if _mins(ns) < _mins(b.end_time) and _mins(b.start_time) < _mins(ne):
                overlap_msgs.append(f'"{b.name}" (untouched, {b.start_time}-{b.end_time}) '
                                    f'would overlap "{slot.name}" ({ns}-{ne})')
    if overlap_msgs:
        return None, ('Would create a new overlap: ' + '; '.join(overlap_msgs) +
                      '. Set after_period on that break first (Settings -> Timetable Slots), then re-run.')

    return (plan, skipped_breaks), None


def run(app, apply_, start_override):
    from models import db, TimetableSlot

    with app.app_context():
        teaching = (TimetableSlot.query.filter_by(is_active=True, is_break=False)
                   .order_by(TimetableSlot.id).all())
        breaks = TimetableSlot.query.filter_by(is_active=True, is_break=True).all()

        if not teaching:
            print('No active teaching periods — nothing to do.')
            return 0

        result, error = _plan(teaching, breaks, start_override)
        if error:
            print(f'ABORTED: {error}')
            return 1
        plan, skipped_breaks = result

        print(f'{"SLOT":<14} {"CURRENT":>16}   ->   {"CORRECTED":>16}   {"CHANGED?"}')
        any_changed = False
        for slot, new_start, new_end in plan:
            cur = f'{slot.start_time}-{slot.end_time}' if slot.start_time else '(unset)'
            new = f'{new_start}-{new_end}'
            changed = (slot.start_time, slot.end_time) != (new_start, new_end)
            any_changed = any_changed or changed
            print(f'{slot.name:<14} {cur:>16}   ->   {new:>16}   {"CHANGED" if changed else ""}')

        for b in skipped_breaks:
            print(f'NOTE: break "{b.name}" has no after_period set — left untouched. '
                  'Set it in Settings -> Timetable Slots if it also needs repositioning.')

        if not any_changed:
            print('\nNo changes needed — already correct.')
            return 0

        if not apply_:
            print('\nDry run only — nothing written. Re-run with --apply to commit this.')
            return 0

        for slot, new_start, new_end in plan:
            slot.start_time, slot.end_time = new_start, new_end
        db.session.commit()

        from utils.timetable_slots import repair_slot_schedule
        repair_slot_schedule()   # cheap, idempotent: just re-syncs `order`

        print('\nApplied and committed.')
        return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--apply', action='store_true', help='Write the changes (default: dry run).')
    ap.add_argument('--subdomain', help='Target one tenant by subdomain (multi-tenant setups).')
    ap.add_argument('--start', help='Override the day-start anchor, e.g. 08:00 '
                    '(default: SchoolSettings school_day_start, else 08:20).')
    args = ap.parse_args(argv)

    if args.subdomain:
        from utils import tenancy, tenant_admin
        tenancy.init_control_plane()
        t = tenancy.get_tenant(args.subdomain)
        if not t or t.status != 'active' or not t.database_url:
            print(f'No active school "{args.subdomain}".')
            return 1
        app = tenant_admin.tenant_app(t.database_url)
    else:
        from app import create_app
        app = create_app()

    return run(app, args.apply, args.start)


if __name__ == '__main__':
    raise SystemExit(main())
