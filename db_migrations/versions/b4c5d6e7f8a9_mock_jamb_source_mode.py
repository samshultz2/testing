"""mock jamb: source_mode (draw from bank vs manual)

Adds ``source_mode`` to ``mock_jamb_exams`` so a mock can be marked to draw its
paper from the central question bank ('bank') or to use its own authored
questions ('manual'). Guarded/idempotent.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-07-19 17:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'b4c5d6e7f8a9'
down_revision = 'a3b4c5d6e7f8'
branch_labels = None
depends_on = None


def _has_column(table, column):
    try:
        return column in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return False


def upgrade():
    if not _has_column('mock_jamb_exams', 'source_mode'):
        with op.batch_alter_table('mock_jamb_exams', schema=None) as b:
            b.add_column(sa.Column('source_mode', sa.String(length=10),
                                   nullable=True, server_default='bank'))


def downgrade():
    pass
