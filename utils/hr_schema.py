"""Lazy, idempotent schema self-heal for post-baseline HR columns.

Production runs with SKIP_CREATE_ALL=1 (Alembic owns the schema), and existing
tenant databases created before a column was added won't get it from
``create_all``. This adds the missing HR columns to whatever database is
currently bound, once per engine, guarded so it never errors. Safe to call at
the top of any HR self-service request — the check is cached per engine URL.

Mirrors utils/mock_jamb_schema.py.
"""
from __future__ import annotations

_ensured = set()   # engine URLs already healed this process


def _cols(inspector, table):
    try:
        return {c['name'] for c in inspector.get_columns(table)}
    except Exception:
        return None


def ensure_hr_schema():
    """Add any missing post-baseline HR columns to the current tenant DB
    (idempotent, best-effort). A no-op after the first call per engine."""
    from models import db
    try:
        engine = db.engine
    except Exception:
        return
    key = str(getattr(engine, 'url', 'default'))
    if key in _ensured:
        return

    from sqlalchemy import inspect, text
    stmts = []
    try:
        insp = inspect(engine)
    except Exception:
        _ensured.add(key)
        return

    sa = _cols(insp, 'staff_attendance')
    if sa is not None and 'clock_out' not in sa:
        stmts.append('ALTER TABLE staff_attendance ADD COLUMN clock_out VARCHAR(5)')

    if stmts:
        try:
            with engine.begin() as conn:
                for s in stmts:
                    try:
                        conn.execute(text(s))
                    except Exception:
                        pass   # column may already exist / concurrent add
        except Exception:
            pass
    _ensured.add(key)
