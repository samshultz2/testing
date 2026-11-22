"""exam_timetables start/end date — the exam window

Revision ID: c3d5e7f9a1b2
Revises: b2c4d6e8f0a1
Create Date: 2026-11-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c3d5e7f9a1b2'
down_revision = 'b2c4d6e8f0a1'
branch_labels = None
depends_on = None


def upgrade():
    cols = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('exam_timetables')}
    with op.batch_alter_table('exam_timetables') as b:
        if 'start_date' not in cols:
            b.add_column(sa.Column('start_date', sa.Date(), nullable=True))
        if 'end_date' not in cols:
            b.add_column(sa.Column('end_date', sa.Date(), nullable=True))


def downgrade():
    cols = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('exam_timetables')}
    with op.batch_alter_table('exam_timetables') as b:
        if 'end_date' in cols:
            b.drop_column('end_date')
        if 'start_date' in cols:
            b.drop_column('start_date')
