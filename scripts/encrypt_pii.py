#!/usr/bin/env python3
"""
One-time: encrypt existing sensitive PII columns at rest (AES-256-GCM).

These columns are now ``EncryptedString`` in the models, so NEW writes are
already encrypted. This backfills EXISTING rows that predate the change. Reads
work either way (``crypto.decrypt`` passes legacy plaintext through), so this is
safe to run whenever — it just turns plaintext-at-rest into ciphertext-at-rest.

Run AFTER setting FIELD_ENCRYPTION_KEY (see .env.example). It:
  1. widens the affected VARCHAR columns to TEXT on PostgreSQL (encrypted tokens
     are longer than the old limits);
  2. re-encrypts any rows still stored as plaintext (idempotent — rows that are
     already ``enc:gcm1:…`` are skipped).

    export FIELD_ENCRYPTION_KEY=...        # or put it in .env
    python scripts/encrypt_pii.py
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

# table -> (columns to encrypt, columns needing VARCHAR->TEXT widening on PG)
_TABLES = {
    'students': (['home_address'], []),
    'staff_members': (
        ['address', 'nok_name', 'nok_phone', 'nok_relationship',
         'bank_name', 'account_number', 'account_name', 'notes'],
        ['address', 'nok_name', 'nok_phone', 'nok_relationship',
         'bank_name', 'account_number', 'account_name'],
    ),
    'discipline_records': (['description', 'action_taken'], []),
    'clinic_visits': (['complaint', 'treatment'], []),
}


def main():
    if not crypto.is_enabled():
        sys.exit('FIELD_ENCRYPTION_KEY is not set — nothing to do. Set it first.')

    app = create_app()
    with app.app_context():
        is_pg = db.engine.url.get_backend_name().startswith('postgresql')
        grand_done = grand_skip = 0
        for table, (enc_cols, widen_cols) in _TABLES.items():
            if is_pg:
                for col in widen_cols:
                    try:
                        db.session.execute(text(
                            f'ALTER TABLE {table} ALTER COLUMN {col} TYPE TEXT'))
                        db.session.commit()
                    except Exception as exc:
                        db.session.rollback()
                        print(f'({table}.{col} widen skipped: {exc})')

            col_list = ', '.join(enc_cols)
            rows = db.session.execute(text(
                f'SELECT id, {col_list} FROM {table}')).fetchall()
            done = skipped = 0
            for row in rows:
                rid = row[0]
                updates, params = [], {'id': rid}
                for i, col in enumerate(enc_cols, start=1):
                    val = row[i]
                    if val is None or crypto.looks_encrypted(val):
                        continue
                    updates.append(f'{col} = :{col}')
                    params[col] = crypto.encrypt(val)
                if updates:
                    db.session.execute(text(
                        f'UPDATE {table} SET {", ".join(updates)} WHERE id = :id'), params)
                    done += 1
                else:
                    skipped += 1
            db.session.commit()
            print(f'{table}: encrypted {done} row(s); {skipped} already encrypted/empty.')
            grand_done += done
            grand_skip += skipped
        print(f'Done — {grand_done} row(s) encrypted, {grand_skip} skipped.')


if __name__ == '__main__':
    main()
