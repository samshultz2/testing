"""mock jamb: question exam_year (past-question year for imports)

Adds ``exam_year`` to ``mock_jamb_questions`` so an imported past question keeps
the year it came from (e.g. ALOC ``examyear``). Guarded/idempotent.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-07-19 11:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'e1f2a3b4c5d6'
down_revision = 'd0e1f2a3b4c5'
branch_labels = None
depends_on = None


def _has_column(table, column):
    try:
        return column in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return False


def upgrade():
    if not _has_column('mock_jamb_questions', 'exam_year'):
        with op.batch_alter_table('mock_jamb_questions', schema=None) as b:
            b.add_column(sa.Column('exam_year', sa.String(length=8), nullable=True))


def downgrade():
    pass
