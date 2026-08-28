"""Lazy, idempotent schema self-heal for the Mock JAMB tables.

Production runs with SKIP_CREATE_ALL=1 (Alembic owns the schema), so the runtime
``ADD COLUMN`` ensure in models is skipped there. When a tenant database has not
yet had the latest Alembic migrations applied, pages that load a
``MockJAMBExam`` (e.g. the blueprint editor) would 500 on a missing column.

This module adds the post-baseline Mock JAMB columns to whatever database is
currently bound, once per engine, guarded so it never errors. It is safe to call
at the top of every Mock JAMB request — the check is cached per engine URL.
"""
from __future__ import annotations

_ensured = set()   # engine URLs already checked this process


def _cols(inspector, table):
    try:
        return {c['name'] for c in inspector.get_columns(table)}
    except Exception:
        return None


def ensure_mock_jamb_schema():
    """Add any missing Mock JAMB columns to the current tenant DB (idempotent,
    best-effort). Cached per engine so the cost is a no-op after the first call."""
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

    ex = _cols(insp, 'mock_jamb_exams')
    if ex is not None:
        add = {
            'is_published': 'BOOLEAN DEFAULT 0',
            'duration_minutes': 'INTEGER DEFAULT 120',
            'questions_per_subject': 'INTEGER',
            'blueprint': 'TEXT',
            'novel_title': 'VARCHAR(150)',
            'source_mode': "VARCHAR(10) DEFAULT 'bank'",
            'eligible_levels': 'VARCHAR(200)',
        }
        for col, ddl in add.items():
            if col not in ex:
                stmts.append(f'ALTER TABLE mock_jamb_exams ADD COLUMN {col} {ddl}')

    mq = _cols(insp, 'mock_jamb_questions')
    if mq is not None:
        add = {
            'section': 'VARCHAR(40)', 'exam_body': "VARCHAR(10) DEFAULT 'JAMB'",
            'difficulty': 'VARCHAR(10)', 'source': 'VARCHAR(20)',
            'source_ref': 'VARCHAR(40)', 'exam_year': 'VARCHAR(8)',
            'needs_image': 'BOOLEAN DEFAULT 0',
            'syllabus_item_code': 'VARCHAR(60)',
        }
        for col, ddl in add.items():
            if col not in mq:
                stmts.append(f'ALTER TABLE mock_jamb_questions ADD COLUMN {col} {ddl}')

    mp = _cols(insp, 'mock_jamb_passages')
    if mp is not None and 'section' not in mp:
        stmts.append('ALTER TABLE mock_jamb_passages ADD COLUMN section VARCHAR(40)')

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

    # Create the imported-syllabus tables if this tenant DB predates them.
    try:
        from models.mock_jamb import MockJAMBSyllabus, MockJAMBSyllabusNode
        db.metadata.create_all(
            bind=engine,
            tables=[MockJAMBSyllabus.__table__, MockJAMBSyllabusNode.__table__],
            checkfirst=True,
        )
    except Exception:
        pass

    _ensured.add(key)
