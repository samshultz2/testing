"""Self-healing for the school-wide ``TimetableSlot`` schedule.

``TimetableSlot.order`` is a hand-maintained integer meant to mirror the
slots' real ``start_time``/``end_time`` — but a slot-extension bug (fixed in
code, but not retroactively in already-written rows) could leave a teaching
period sharing the exact same clock time as a break that already ran right
after it (e.g. "Period 9" starting at 14:10, the same moment "Long Break"
begins), with ``order`` then disagreeing with the actual times too. Both the
timetable view/PDF and the generator's period-number-to-slot mapping sort by
``order``, so a mismatch like that renders a nonsensical, overlapping-looking
schedule.

``repair_slot_schedule()`` detects and fixes exactly that: a teaching period
overlapping a break's time range gets pushed to start right after the break
ends (breaks — an admin's own configured time — are never moved), and every
active slot's ``order`` is then re-derived from the corrected clock times so
display and mapping stay in sync. It's idempotent: a school whose slots are
already conflict-free sees no changes.
"""
from datetime import timedelta, datetime as _dt


def repair_slot_schedule():
    """Fix any teaching TimetableSlot whose time overlaps a break's, and
    re-sync every active slot's ``order`` to match real clock time. Commits
    its own change (some callers run this from a plain page view, which
    otherwise never commits) and is best-effort: any failure is rolled back
    and swallowed so a repair attempt can never break the page that
    triggered it. Returns True if anything was changed."""
    from models import db, TimetableSlot

    try:
        slots = (TimetableSlot.query.filter_by(is_active=True)
                 .filter(TimetableSlot.start_time.isnot(None), TimetableSlot.end_time.isnot(None))
                 .order_by(TimetableSlot.start_time, TimetableSlot.order).all())

        changed = False
        prev_end = None
        for s in slots:
            if prev_end is not None and s.start_time < prev_end:
                if s.is_break:
                    # Never silently move an admin-configured break's own
                    # time — only a colliding teaching period gets pushed.
                    prev_end = max(prev_end, s.end_time)
                    continue
                dur = (timedelta(minutes=s.duration_minutes) if s.duration_minutes
                       else (_dt.combine(_dt.today(), s.end_time)
                             - _dt.combine(_dt.today(), s.start_time)))
                new_start = prev_end
                new_end = (_dt.combine(_dt.today(), new_start) + dur).time()
                s.start_time, s.end_time = new_start, new_end
                changed = True
            prev_end = s.end_time if prev_end is None else max(prev_end, s.end_time)

        if changed:
            db.session.flush()

        # Re-derive `order` from actual clock time for every active slot —
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
        return False
