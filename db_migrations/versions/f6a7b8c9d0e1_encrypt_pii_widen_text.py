"""widen staff PII columns to TEXT for at-rest field encryption

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-03 09:00:00.000000

Several StaffMember columns are now EncryptedString (AES-256-GCM) at rest. The
ciphertext token (``enc:gcm1:<base64>``) is much longer than the old
``VARCHAR(N)`` limits, so widen those columns to TEXT on PostgreSQL. SQLite does
not enforce VARCHAR length, so it needs no change; new deploys via
``db.create_all()`` already create these as TEXT.

Schema-only and idempotent (``ALTER … TYPE TEXT`` is a no-op if already TEXT).
Re-encrypting existing plaintext rows is a separate manual step —
``scripts/encrypt_pii.py`` — run after FIELD_ENCRYPTION_KEY is configured.
"""
from alembic import op


revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None

_COLS = ['address', 'nok_name', 'nok_phone', 'nok_relationship',
         'bank_name', 'account_number', 'account_name']


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return                      # SQLite: VARCHAR length not enforced
    for col in _COLS:
        op.execute(f'ALTER TABLE staff_members ALTER COLUMN {col} TYPE TEXT')


def downgrade():
    # Intentionally a no-op: narrowing back to VARCHAR would truncate any
    # encrypted tokens already stored. TEXT is a safe superset.
    pass
