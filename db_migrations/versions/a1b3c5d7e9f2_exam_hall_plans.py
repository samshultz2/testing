"""exam_hall_plans — saved exam hall allocations

Revision ID: a1b3c5d7e9f2
Revises: 9a3c5e7b1d2f
Create Date: 2026-11-22 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b3c5d7e9f2'
down_revision = '9a3c5e7b1d2f'
branch_labels = None
depends_on = None


def upgrade():
    if not sa.inspect(op.get_bind()).has_table('exam_hall_plans'):
        op.create_table(
            'exam_hall_plans',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id')),
            sa.Column('term_id', sa.Integer(), sa.ForeignKey('terms.id')),
            sa.Column('name', sa.String(150), nullable=False),
            sa.Column('params', sa.Text()),
            sa.Column('snapshot', sa.Text(), nullable=False),
            sa.Column('total_students', sa.Integer(), server_default='0'),
            sa.Column('hall_count', sa.Integer(), server_default='0'),
            sa.Column('created_by', sa.String(100)),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('updated_at', sa.DateTime()),
        )
        op.create_index('ix_exam_hall_plans_branch_id', 'exam_hall_plans', ['branch_id'])


def downgrade():
    if sa.inspect(op.get_bind()).has_table('exam_hall_plans'):
        op.drop_index('ix_exam_hall_plans_branch_id', table_name='exam_hall_plans')
        op.drop_table('exam_hall_plans')
