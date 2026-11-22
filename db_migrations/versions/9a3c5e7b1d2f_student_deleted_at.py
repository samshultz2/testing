"""student deleted_at — when a student was moved to the trash

Revision ID: 9a3c5e7b1d2f
Revises: 8f2b4d6a1c3e
Create Date: 2026-11-22 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '9a3c5e7b1d2f'
down_revision = '8f2b4d6a1c3e'
branch_labels = None
depends_on = None


def upgrade():
    cols = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('students')}
    if 'deleted_at' not in cols:
        with op.batch_alter_table('students') as b:
            b.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))


def downgrade():
    cols = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('students')}
    if 'deleted_at' in cols:
        with op.batch_alter_table('students') as b:
            b.drop_column('deleted_at')
