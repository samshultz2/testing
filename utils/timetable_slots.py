"""Self-healing for the school-wide ``TimetableSlot`` schedule.

Two repair strategies, chosen automatically. Both share one hard rule
inherited from the original design: **a teaching period's own start/end time
is authoritative and this module never rewrites it** — only a break ever
moves. That matters because periods aren't always perfectly back-to-back (a
school may leave a genuine gap for some reason of its own); recomputing every
period's time from a fixed chain would silently erase gaps like that.

1. **Rule-based** (used once every active break has ``after_period`` set —
   the normal case after the backfill migration). Each break declares which
   teaching period it belongs immediately after (1-based, among teaching
   periods sorted by their own current ``start_time`` — the same ordering
   basis the rest of the app already trusts). The break is placed to start
   exactly when that period currently ends. This is definitive: unlike the
   overlap check below, it will move a break *earlier* as well as later if
   that's what the rule says, which is exactly what's needed when a break
   ended up sitting before a period it should follow (no overlap involved,
   so nothing about the raw clock times alone reveals that it's "wrong").

2. **Overlap-only** (fallback for any break still missing ``after_period``).
   The historical behaviour: a break that overlaps a teaching period's clock
   time is pushed to right after it, while a break that doesn't collide with
   anything is left exactly where it is, since there's no declared rule to
   check it against.

``repair_slot_schedule()`` runs whichever applies, then re-derives every
active slot's ``order`` from the corrected clock times so display and the
generator's period mapping stay in sync. It's idempotent: a school whose
slots already match their declared rule (or, lacking one, are conflict-free)
sees no changes.
"""
from datetime import timedelta, datetime as _dt


def _duration(slot, default_minutes):
    if slot.duration_minutes:
        return timedelta(minutes=slot.duration_minutes)
    if slot.start_time and slot.end_time:
        d = (_dt.combine(_dt.today(), slot.end_time)
             - _dt.combine(_dt.today(), slot.start_time))
        if d.total_seconds() > 0:
            return d
    return timedelta(minutes=default_minutes)


def _rebuild_from_after_period(teaching, breaks):
    """Reposition each break to start exactly when the teaching period its
    ``after_period`` names currently ends. Teaching periods' own times are
    never touched. ``teaching`` must already be sorted by current
    ``start_time``. Returns True if anything changed."""
    teaching = [t for t in teaching if t.start_time and t.end_time]
    if not teaching:
        return False

    changed = False
    n = len(teaching)
    for b in breaks:
        i = max(1, min(b.after_period, n))   # break "after period 0" has no
        if b.after_period < 1:               # anchor without moving a period — skip it
            continue
        anchor_end = teaching[i - 1].end_time
        dur = _duration(b, 30)
        new_start = anchor_end
        new_end = (_dt.combine(_dt.today(), new_start) + dur).time()
        if (b.start_time, b.end_time) != (new_start, new_end):
            b.start_time, b.end_time = new_start, new_end
            changed = True

    return changed


def _repair_by_overlap(teaching, breaks):
    """The historical conservative repair: push a break that overlaps a
    period to right after it; leave everything else untouched. Returns True
    if anything changed."""
    changed = False
    for _ in range(20):   # generous cap — real schedules have few slots
        t_slots = [t for t in teaching if t.start_time and t.end_time]
        b_slots = [b for b in breaks if b.start_time and b.end_time]
        moved = False
        for b in b_slots:
            overlapping = [t for t in t_slots
                          if t.start_time < b.end_time and b.start_time < t.end_time]
            if not overlapping:
                continue
            latest_end = max(t.end_time for t in overlapping)
            dur = _duration(b, 30)
            new_start = latest_end
            new_end = (_dt.combine(_dt.today(), new_start) + dur).time()
            if (b.start_time, b.end_time) != (new_start, new_end):
                b.start_time, b.end_time = new_start, new_end
                changed = True
                moved = True
        if not moved:
            break
    return changed


def repair_slot_schedule():
    """Definitively fix the active slot schedule's ordering (see module
    docstring for the two strategies), then re-sync every active slot's
    ``order`` to match real clock time. Commits its own change (some callers
    run this from a plain page view, which otherwise never commits) and is
    best-effort: any failure is rolled back and swallowed so a repair attempt
    can never break the page that triggered it. Returns True if anything was
    changed."""
    from models import db, TimetableSlot

    try:
        teaching = (TimetableSlot.query.filter_by(is_active=True, is_break=False)
                   .order_by(TimetableSlot.start_time, TimetableSlot.slot_number).all())
        breaks = TimetableSlot.query.filter_by(is_active=True, is_break=True).all()

        if teaching and breaks and all(b.after_period is not None for b in breaks):
            changed = _rebuild_from_after_period(teaching, breaks)
        else:
            changed = _repair_by_overlap(teaching, breaks)

        # Re-derive `order` for every active slot from actual clock time —
        # cheap, and keeps the two fields from ever silently drifting apart
        # again, regardless of what caused this particular pass's fix (or none).
        ordered = (TimetableSlot.query.filter_by(is_active=True)
                   .order_by(TimetableSlot.start_time, TimetableSlot.order).all())
        for i, s in enumerate(ordered, start=1):
            if s.order != i:
                s.order = i
                changed = True

        if changed:
            db.session.commit()
        return changed
    except Exception:
        db.session.rollback()
        try:
            from flask import current_app
            current_app.logger.exception('repair_slot_schedule failed')
        except Exception:
            pass
        return False
