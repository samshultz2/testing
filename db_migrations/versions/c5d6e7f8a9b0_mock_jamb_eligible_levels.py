"""mock jamb: eligible_levels (which classes may sit online)

Adds ``eligible_levels`` to ``mock_jamb_exams`` — a comma-separated list of
SchoolClass names allowed to sit a mock online. Empty/NULL means the graduating
SSS3 class only (the JAMB cohort), which is the default. Guarded/idempotent.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-07-23 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'c5d6e7f8a9b0'
down_revision = 'b4c5d6e7f8a9'
branch_labels = None
depends_on = None


def _has_column(table, column):
    try:
        return column in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return False


def upgrade():
    if not _has_column('mock_jamb_exams', 'eligible_levels'):
        with op.batch_alter_table('mock_jamb_exams', schema=None) as b:
            b.add_column(sa.Column('eligible_levels', sa.String(length=200), nullable=True))


def downgrade():
    pass
