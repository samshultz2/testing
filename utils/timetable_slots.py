"""Self-healing for the school-wide ``TimetableSlot`` schedule.

Two repair strategies, chosen automatically:

1. **Rule-based** (used once every active break has ``after_period`` set —
   the normal case after the backfill migration). Each break declares which
   teaching period it belongs immediately after (1-based, by the period's own
   ``slot_number`` — its positional identity, unaffected by any clock-time
   drift). The whole day is walked in that declared order — period 1, period
   2, ..., inserting each break at its declared position — and every slot's
   start/end time is (re)computed from there, preserving each row's own
   ``duration_minutes``. This is definitive: unlike the overlap check below,
   it will move a break *earlier* as well as later if that's what the rule
   says, which is exactly what's needed when a break ended up sitting before
   a period it should follow (no overlap involved, so nothing about the raw
   clock times alone reveals that it's "wrong").

2. **Overlap-only** (fallback for any break still missing ``after_period``).
   The historical behaviour: a break that overlaps a teaching period's clock
   time is pushed to right after it — teaching periods are authoritative and
   never moved, only the break — while a break that doesn't collide with
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
    """Recompute every slot's start/end time by walking teaching periods in
    ``slot_number`` order and inserting each break right after the period
    its ``after_period`` names. Returns True if anything changed."""
    if not teaching or not teaching[0].start_time:
        return False

    by_after = {}
    for b in breaks:
        n = max(0, min(b.after_period, len(teaching)))
        by_after.setdefault(n, []).append(b)

    changed = False
    cursor = _dt.combine(_dt.today(), teaching[0].start_time)

    def place(slot, default_minutes):
        nonlocal cursor, changed
        end = cursor + _duration(slot, default_minutes)
        new_start, new_end = cursor.time(), end.time()
        if (slot.start_time, slot.end_time) != (new_start, new_end):
            slot.start_time, slot.end_time = new_start, new_end
            changed = True
        cursor = end

    for b in by_after.get(0, []):
        place(b, 30)
    for i, p in enumerate(teaching, start=1):
        place(p, 40)
        for b in by_after.get(i, []):
            place(b, 30)

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
                   .order_by(TimetableSlot.slot_number, TimetableSlot.id).all())
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
