#!/usr/bin/env python3
"""
One-time: encrypt existing student portal passwords at rest (AES-256-GCM).

Run this AFTER setting FIELD_ENCRYPTION_KEY (see .env.example). It:
  1. widens students.portal_password_plain to TEXT on PostgreSQL (encrypted
     tokens are longer than the old VARCHAR(60));
  2. encrypts any rows still stored as plaintext (idempotent — already-encrypted
     rows are skipped).

    export FIELD_ENCRYPTION_KEY=...        # or put it in .env
    python scripts/encrypt_portal_passwords.py
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
from utils import crypto  # noqa: E402


def main():
    if not crypto.is_enabled():
        sys.exit('FIELD_ENCRYPTION_KEY is not set — nothing to do. Set it first.')

    app = create_app()
    with app.app_context():
        is_pg = db.engine.url.get_backend_name().startswith('postgresql')
        if is_pg:
            try:
                db.session.execute(text(
                    'ALTER TABLE students ALTER COLUMN portal_password_plain TYPE TEXT'))
                db.session.commit()
                print('Widened students.portal_password_plain to TEXT.')
            except Exception as exc:
                db.session.rollback()
                print(f'(column widen skipped: {exc})')

        rows = db.session.execute(text(
            'SELECT id, portal_password_plain FROM students '
            'WHERE portal_password_plain IS NOT NULL')).fetchall()
        done = skipped = 0
        for sid, val in rows:
            if crypto.looks_encrypted(val):
                skipped += 1
                continue
            enc = crypto.encrypt(val)
            db.session.execute(
                text('UPDATE students SET portal_password_plain = :v WHERE id = :id'),
                {'v': enc, 'id': sid})
            done += 1
        db.session.commit()
        print(f'Encrypted {done} portal password(s); {skipped} already encrypted.')


if __name__ == '__main__':
    main()
