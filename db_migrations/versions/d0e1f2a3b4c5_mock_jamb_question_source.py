"""mock jamb: question provenance (source / source_ref for imports)

Adds ``source`` and ``source_ref`` to ``mock_jamb_questions`` so imported
questions (e.g. from the ALOC questions API) can be attributed and de-duplicated
by their external id. Guarded/idempotent.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-07-19 09:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'd0e1f2a3b4c5'
down_revision = 'c9d0e1f2a3b4'
branch_labels = None
depends_on = None


def _has_column(table, column):
    try:
        return column in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return False


def upgrade():
    with op.batch_alter_table('mock_jamb_questions', schema=None) as b:
        if not _has_column('mock_jamb_questions', 'source'):
            b.add_column(sa.Column('source', sa.String(length=20), nullable=True))
        if not _has_column('mock_jamb_questions', 'source_ref'):
            b.add_column(sa.Column('source_ref', sa.String(length=40), nullable=True))


def downgrade():
    pass
