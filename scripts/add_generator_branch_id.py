#!/usr/bin/env python3
"""One-shot: add branch_id to the per-branch generator tables on every tenant
database and backfill existing rows to that school's default (HQ) branch.

The generator's branch split ships as a lazy per-request self-heal
(utils.generator_schema); this script does the same migration eagerly and
verbosely across all schools so you don't have to touch each page, and so any
real error surfaces here instead of as a 500. Idempotent — safe to re-run.

    python scripts/add_generator_branch_id.py                 # all active schools
    python scripts/add_generator_branch_id.py --subdomain myschool
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text   # noqa: E402

from utils import tenancy, tenant_admin                # noqa: E402
from utils.generator_schema import _TABLES, _swap_uniques_postgres   # noqa: E402


def _default_branch_id(conn):
    try:
        row = conn.execute(text(
            "SELECT id FROM branches ORDER BY is_default DESC, id ASC LIMIT 1")).first()
        return row[0] if row else None
    except Exception:
        return None


def heal_engine(url):
    """Add branch_id + backfill + swap uniques on one tenant DB (autocommit, so a
    failing secondary step never rolls back the ADD COLUMNs). Returns a summary."""
    eng = create_engine(url)
    added, backfilled, errors = [], [], []
    try:
        insp = inspect(eng)
        is_pg = eng.dialect.name == 'postgresql'
        with eng.connect() as base:
            conn = base.execution_options(isolation_level='AUTOCOMMIT')
            bid = _default_branch_id(conn)
            for t in _TABLES:
                try:
                    cols = {c['name'] for c in insp.get_columns(t)}
                except Exception:
                    continue                      # table absent — skip
                if 'branch_id' not in cols:
                    try:
                        conn.execute(text(f'ALTER TABLE {t} ADD COLUMN branch_id INTEGER'))
                        added.append(t)
                    except Exception as e:
                        errors.append(f'ADD {t}: {e}')
                if bid is not None:
                    try:
                        r = conn.execute(text(
                            f'UPDATE {t} SET branch_id = :b WHERE branch_id IS NULL'), {'b': bid})
                        if r.rowcount:
                            backfilled.append(f'{t}={r.rowcount}')
                    except Exception as e:
                        errors.append(f'BACKFILL {t}: {e}')
            if is_pg:
                try:
                    _swap_uniques_postgres(conn)
                except Exception as e:
                    errors.append(f'UNIQUE swap: {e}')
    finally:
        eng.dispose()
    return added, backfilled, errors


def main(argv=None):
    ap = argparse.ArgumentParser(description='Add generator branch_id to tenant DBs.')
    ap.add_argument('--subdomain', help='Only migrate this one school.')
    args = ap.parse_args(argv)
    tenancy.init_control_plane()

    if args.subdomain:
        t = tenancy.get_tenant(args.subdomain)
        if not t or not t.database_url:
            print(f'No school "{args.subdomain}".')
            return 1
        targets = [t]
    else:
        targets = tenant_admin.active_tenants()

    if not targets:
        print('No active schools.')
        return 0

    failures = 0
    for t in targets:
        try:
            added, backfilled, errors = heal_engine(t.database_url)
            note = []
            if added:
                note.append(f'added {len(added)} col(s)')
            if backfilled:
                note.append('backfilled ' + ', '.join(backfilled))
            if not added and not backfilled:
                note.append('already up to date')
            print(f'✓ {t.subdomain}: {"; ".join(note)}')
            for e in errors:
                print(f'    ! {e}')
        except Exception as e:
            failures += 1
            print(f'✗ {t.subdomain}: {e}')
    print(f'\nDone: {len(targets) - failures}/{len(targets)} schools processed.')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
