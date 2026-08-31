"""mock jamb: questions_per_subject (random draw per candidate)

Adds a nullable ``questions_per_subject`` column to ``mock_jamb_exams`` so an
admin can draw a random subset of each subject's questions per candidate (NULL =
serve all). Idempotent.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-18 14:10:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def _has_column(table, column):
    try:
        return column in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return False


def upgrade():
    if not _has_column('mock_jamb_exams', 'questions_per_subject'):
        with op.batch_alter_table('mock_jamb_exams', schema=None) as b:
            b.add_column(sa.Column('questions_per_subject', sa.Integer(), nullable=True))


def downgrade():
    if _has_column('mock_jamb_exams', 'questions_per_subject'):
        with op.batch_alter_table('mock_jamb_exams', schema=None) as b:
            b.drop_column('questions_per_subject')
