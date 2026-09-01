"""Lazy, idempotent schema self-heal for the subjects.for_junior/for_senior
columns (JSS/SSS classification).

Production runs with SKIP_CREATE_ALL=1 (Alembic owns the schema), and
existing tenant databases created before these columns were added won't get
them from ``create_all``. This adds them to whatever database is currently
bound, once per engine, guarded so it never errors. Existing subjects default
to TRUE on both — they keep showing everywhere they already did until an
admin narrows one explicitly.

Mirrors utils/hr_schema.py.
"""
from __future__ import annotations

_ensured = set()   # engine URLs already healed this process


def ensure_subjects_schema():
    """Add subjects.for_junior/for_senior to the current tenant DB if
    missing (idempotent, best-effort). A no-op after the first call per
    engine."""
    from models import db
    try:
        engine = db.engine
    except Exception:
        return
    key = str(getattr(engine, 'url', 'default'))
    if key in _ensured:
        return

    from sqlalchemy import inspect, text
    try:
        insp = inspect(engine)
        cols = {c['name'] for c in insp.get_columns('subjects')}
    except Exception:
        _ensured.add(key)
        return

    stmts = []
    if 'for_junior' not in cols:
        stmts.append('ALTER TABLE subjects ADD COLUMN for_junior BOOLEAN DEFAULT TRUE')
    if 'for_senior' not in cols:
        stmts.append('ALTER TABLE subjects ADD COLUMN for_senior BOOLEAN DEFAULT TRUE')

    if stmts:
        try:
            with engine.begin() as conn:
                for s in stmts:
                    try:
                        conn.execute(text(s))
                    except Exception:
                        pass   # column may already exist / concurrent add
                # Backfill any NULLs from a bare ADD COLUMN on engines that
                # don't apply DEFAULT to existing rows (older SQLite).
                try:
                    conn.execute(text(
                        'UPDATE subjects SET for_junior = TRUE WHERE for_junior IS NULL'))
                    conn.execute(text(
                        'UPDATE subjects SET for_senior = TRUE WHERE for_senior IS NULL'))
                except Exception:
                    pass
        except Exception:
            pass
    _ensured.add(key)
