#!/usr/bin/env python3
"""Bring the database schema up to date WITHOUT psql or Alembic.

Runs the app's own self-heal (utils.finance_ledger.ensure_tables) against the
configured database — creating any newer tables and adding any newer columns
(e.g. students.graduate_status) that post-date the schema baseline. Uses the
app's own DATABASE_URL, so you don't need psql, credentials, or the right role.

    python scripts/heal_db.py

In multi-tenant mode it heals the primary DB and every active school's DB too.
Safe to run any time — it only adds what's missing (idempotent).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _has_col(engine, table, column):
    from sqlalchemy import inspect
    try:
        return column in {c['name'] for c in inspect(engine).get_columns(table)}
    except Exception:
        return None                           # table/DB not reachable


def _direct_add_graduate_status(engine):
    """Last-resort, fully transparent add of students.graduate_status. Uses the
    database's own idempotency (ADD COLUMN IF NOT EXISTS on Postgres) and prints
    the real exception if it fails, so the true blocker (e.g. permissions) is
    visible instead of hidden."""
    from sqlalchemy import text
    ddl = ('ALTER TABLE students ADD COLUMN IF NOT EXISTS graduate_status VARCHAR(40)'
           if engine.dialect.name == 'postgresql'
           else 'ALTER TABLE students ADD COLUMN graduate_status VARCHAR(40)')
    try:
        with engine.begin() as conn:
            conn.execute(text(ddl))
    except Exception as e:
        print(f'      direct ALTER failed: {type(e).__name__}: {e}')


def main():
    from app import create_app
    from utils.finance_ledger import ensure_tables

    app = create_app()
    with app.app_context():
        ensure_tables()                       # primary / single-school DB
        print('✓ primary database healed')

        if app.config.get('MULTI_TENANT'):
            from sqlalchemy import create_engine
            from utils import tenancy
            # Heal EVERY tenant that has a database — not only 'active' ones, so a
            # school in trial/grace also gets the schema fix.
            targets = [t for t in tenancy.list_tenants() if t.database_url]
            ok = 0
            for t in targets:
                eng = create_engine(t.database_url)
                try:
                    ensure_tables(bind=eng)
                    # verify the column that has been 500ing dashboards
                    col = _has_col(eng, 'students', 'graduate_status')
                    if col is False:
                        # Still missing — attempt a direct, transparent repair and
                        # print the REAL reason if it fails (permissions, etc.).
                        _direct_add_graduate_status(eng)
                        col = _has_col(eng, 'students', 'graduate_status')
                    mark = ('graduate_status ✓' if col else
                            ('no students table' if col is None else 'graduate_status STILL MISSING'))
                    ok += 1
                    print(f'  ✓ {t.subdomain}  ({mark})')
                except Exception as e:
                    print(f'  ✗ {t.subdomain}: {e}')
                finally:
                    eng.dispose()
            print(f'Done: {ok}/{len(targets)} school database(s) healed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
