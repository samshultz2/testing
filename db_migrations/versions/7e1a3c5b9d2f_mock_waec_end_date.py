"""mock_waec_exams.end_date — exams run over several days

Revision ID: 7e1a3c5b9d2f
Revises: 6d9f2b3c4e5a
Create Date: 2026-11-17 06:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '7e1a3c5b9d2f'
down_revision = '6d9f2b3c4e5a'
branch_labels = None
depends_on = None


def _has_column(table, column):
    return column in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    if not _has_column('mock_waec_exams', 'end_date'):
        with op.batch_alter_table('mock_waec_exams', schema=None) as batch_op:
            batch_op.add_column(sa.Column('end_date', sa.Date(), nullable=True))


def downgrade():
    if _has_column('mock_waec_exams', 'end_date'):
        with op.batch_alter_table('mock_waec_exams', schema=None) as batch_op:
            batch_op.drop_column('end_date')
