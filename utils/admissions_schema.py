"""Lazy, idempotent schema self-heal for post-baseline admissions columns.

Production runs with SKIP_CREATE_ALL=1 (Alembic owns the schema), and tenant
databases created before a column existed won't get it from ``create_all``.
This adds the missing emergency-contact columns to whatever database is
currently bound, once per engine, guarded so it never errors.

Mirrors utils/hr_schema.py.
"""
from __future__ import annotations

_ensured = set()   # engine URLs already healed this process

_APPLICANT_COLUMNS = {
    'emergency_name': 'VARCHAR(100)',
    'emergency_phone': 'VARCHAR(20)',
    'emergency_relationship': 'VARCHAR(40)',
    'emergency_address': 'VARCHAR(255)',
    'country': 'VARCHAR(60)',
    'state_of_origin': 'VARCHAR(60)',
    'lga': 'VARCHAR(80)',
    'father_occupation': 'VARCHAR(100)',
    'languages_spoken': 'VARCHAR(120)',
    'blood_group': 'VARCHAR(6)',
    'genotype': 'VARCHAR(6)',
}


def _cols(inspector, table):
    try:
        return {c['name'] for c in inspector.get_columns(table)}
    except Exception:
        return None


def ensure_admissions_schema():
    """Add any missing post-baseline admissions columns to the current tenant
    DB (idempotent, best-effort). A no-op after the first call per engine."""
    from models import db
    try:
        engine = db.session.get_bind()
    except Exception:
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
        have = _cols(insp, 'applicants')
    except Exception:
        _ensured.add(key)
        return

    if have is not None:
        for name, ddl in _APPLICANT_COLUMNS.items():
            if name in have:
                continue
            try:
                with engine.begin() as conn:
                    if engine.dialect.name == 'sqlite':
                        conn.execute(text(f'ALTER TABLE applicants ADD COLUMN {name} {ddl}'))
                    else:
                        conn.execute(text(
                            f'ALTER TABLE applicants ADD COLUMN IF NOT EXISTS {name} {ddl}'))
            except Exception:
                pass   # best-effort; a concurrent add or race is harmless

    # Create the applicant_photos table on tenant DBs that predate it.
    try:
        from models import ApplicantPhoto
        ApplicantPhoto.__table__.create(bind=engine, checkfirst=True)
    except Exception:
        pass

    _ensured.add(key)
