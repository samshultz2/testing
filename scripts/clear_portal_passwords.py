#!/usr/bin/env python3
"""
One-time: wipe the legacy recoverable portal-password copy.

Portal passwords are now stored HASH-ONLY (see models/models/student.py). This
script NULLs the old `students.portal_password_plain` column so the previously
recoverable (encrypted-but-reversible) PINs no longer exist at rest. Login is
unaffected — it uses `portal_password_hash`. Students keep their current PIN
until an admin regenerates it; only the recoverable copy is removed.

Idempotent and safe to run repeatedly. The physical column is left in place
(no destructive DDL on production) — it is simply emptied and no longer written.

    python scripts/clear_portal_passwords.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except Exception:
    pass

from sqlalchemy import text  # noqa: E402
from app import create_app  # noqa: E402
from models import db  # noqa: E402


def main():
    app = create_app()
    with app.app_context():
        # The column may already be gone on a fresh install; tolerate that.
        try:
            res = db.session.execute(text(
                'UPDATE students SET portal_password_plain = NULL '
                'WHERE portal_password_plain IS NOT NULL'))
            db.session.commit()
            n = res.rowcount if res.rowcount is not None else 0
            print(f'Cleared recoverable portal password copy on {n} student(s).')
        except Exception as exc:
            db.session.rollback()
            print(f'Nothing to clear (column absent or already empty): {exc}')


if __name__ == '__main__':
    main()
