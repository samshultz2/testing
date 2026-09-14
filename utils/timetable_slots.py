"""Self-healing for the school-wide ``TimetableSlot`` schedule.

``TimetableSlot.order`` is a hand-maintained integer meant to mirror the
slots' real ``start_time``/``end_time`` — but a slot-extension bug could
leave a newly-added teaching period sharing (or straddling) the exact clock
time of a break that already ran right after the previous last period (e.g.
"Period 9" landing on the same start time as "Long Break", which used to be
the last thing in the day). Teaching periods must never be displaced by a
break — a period's own time is authoritative; a break that sits in the way
of one is the thing that moves, to right after the period(s) it collides
with. (A break that doesn't collide with anything — e.g. a genuine mid-day
break between two periods — is left exactly where it is.)

``repair_slot_schedule()`` applies exactly that rule, then re-derives every
active slot's ``order`` from the corrected clock times so display and the
generator's period mapping stay in sync. It's idempotent: a school whose
slots are already conflict-free sees no changes.
"""
from datetime import timedelta, datetime as _dt


def repair_slot_schedule():
    """Push any break overlapping a teaching period to right after it (never
    the other way round), then re-sync every active slot's ``order`` to
    match real clock time. Commits its own change (some callers run this
    from a plain page view, which otherwise never commits) and is
    best-effort: any failure is rolled back and swallowed so a repair
    attempt can never break the page that triggered it. Returns True if
    anything was changed."""
    from models import db, TimetableSlot

    try:
        changed = False

        # Resolve break-vs-period overlaps by moving the break. Iterate to a
        # fixed point: moving one break later can newly overlap the next
        # slot in the day, so re-scan until nothing moves. Each break only
        # ever moves later, never earlier, so this always terminates.
        for _ in range(20):   # generous cap — real schedules have few slots
            teaching = (TimetableSlot.query.filter_by(is_active=True, is_break=False)
                       .filter(TimetableSlot.start_time.isnot(None),
                               TimetableSlot.end_time.isnot(None)).all())
            breaks = (TimetableSlot.query.filter_by(is_active=True, is_break=True)
                     .filter(TimetableSlot.start_time.isnot(None),
                             TimetableSlot.end_time.isnot(None)).all())
            moved = False
            for b in breaks:
                overlapping = [t for t in teaching
                              if t.start_time < b.end_time and b.start_time < t.end_time]
                if not overlapping:
                    continue
                latest_end = max(t.end_time for t in overlapping)
                dur = (timedelta(minutes=b.duration_minutes) if b.duration_minutes
                       else (_dt.combine(_dt.today(), b.end_time)
                             - _dt.combine(_dt.today(), b.start_time)))
                new_start = latest_end
                new_end = (_dt.combine(_dt.today(), new_start) + dur).time()
                if (b.start_time, b.end_time) != (new_start, new_end):
                    b.start_time, b.end_time = new_start, new_end
                    changed = True
                    moved = True
            if moved:
                db.session.flush()
            else:
                break

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
