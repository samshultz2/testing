"""mock jamb: novel_title (JAMB-approved novel per mock)

Adds ``novel_title`` to ``mock_jamb_exams`` so an English paper draws its
Recommended-Novel section only from questions tagged with that mock's approved
novel. Guarded/idempotent.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-19 13:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'f2a3b4c5d6e7'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def _has_column(table, column):
    try:
        return column in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return False


def upgrade():
    if not _has_column('mock_jamb_exams', 'novel_title'):
        with op.batch_alter_table('mock_jamb_exams', schema=None) as b:
            b.add_column(sa.Column('novel_title', sa.String(length=150), nullable=True))


def downgrade():
    pass
