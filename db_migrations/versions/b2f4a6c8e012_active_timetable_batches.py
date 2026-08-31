"""active_timetable_batches table

Revision ID: b2f4a6c8e012
Revises: f1a2b3c4d5e6
Create Date: 2026-06-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2f4a6c8e012'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('active_timetable_batches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('school_level', sa.String(length=10), nullable=True),
    sa.Column('batch_id', sa.String(length=50), nullable=False),
    sa.Column('set_at', sa.DateTime(), nullable=True),
    sa.Column('set_by_user_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['branch_id'], ['branches.id']),
    sa.ForeignKeyConstraint(['set_by_user_id'], ['users.id']),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('branch_id', 'school_level', name='uq_active_timetable_branch_level')
    )


def downgrade():
    op.drop_table('active_timetable_batches')
