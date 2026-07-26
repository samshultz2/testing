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


def main():
    from app import create_app
    from utils.finance_ledger import ensure_tables

    app = create_app()
    with app.app_context():
        ensure_tables()                       # primary / single-school DB
        print('✓ primary database healed')

        if app.config.get('MULTI_TENANT'):
            from sqlalchemy import create_engine
            from utils import tenant_admin
            targets = tenant_admin.active_tenants()
            ok = 0
            for t in targets:
                eng = create_engine(t.database_url)
                try:
                    ensure_tables(bind=eng)
                    ok += 1
                    print(f'  ✓ {t.subdomain}')
                except Exception as e:
                    print(f'  ✗ {t.subdomain}: {e}')
                finally:
                    eng.dispose()
            print(f'Done: {ok}/{len(targets)} school database(s) healed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
