"""Lazy, idempotent self-heal for the staff-invite enhancements (preset position +
per-invite field selection). Adds the ``position`` and ``fields`` columns to the
existing ``staff_invites`` table on whatever tenant DB is bound, once per engine.
Mirrors utils/university_schema.py — create_all adds new tables but never new
columns to an existing one.
"""
from __future__ import annotations

_ensured = set()


def ensure_staff_invite_schema():
    from models import db
    try:
        engine = db.engine
    except Exception:
        return
    key = str(getattr(engine, 'url', 'default'))
    if key in _ensured:
        return

    from sqlalchemy import inspect, text
    adds = {'position': 'VARCHAR(80)', 'fields': 'TEXT'}
    columns_ok = False
    try:
        existing = {c['name'] for c in inspect(engine).get_columns('staff_invites')}
        for name, ddl in adds.items():
            if name in existing:
                continue
            try:
                with engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE staff_invites ADD COLUMN IF NOT EXISTS {name} {ddl}'))
            except Exception:
                try:
                    with engine.begin() as conn:
                        conn.execute(text(f'ALTER TABLE staff_invites ADD COLUMN {name} {ddl}'))
                except Exception:
                    pass
        present = {c['name'] for c in inspect(engine).get_columns('staff_invites')}
        columns_ok = all(n in present for n in adds)
    except Exception:
        db.session.rollback()

    if columns_ok:
        _ensured.add(key)
