"""timetable generator: fixed period rules

Adds gen_fixed_period_rules — pins a subject to one specific period number
for one class (optionally one specific arm): whatever day it lands on, it
must always be at that exact period. E.g. SSS2 Lily's Chemistry must always
be period 2, whichever day(s) of the week it's scheduled.

Revision ID: b7c8d9e0f1a2
Revises: d1e2f3a4b5c6
Create Date: 2026-09-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b7c8d9e0f1a2'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def _has_table(table):
    try:
        return table in set(sa.inspect(op.get_bind()).get_table_names())
    except Exception:
        return False


def upgrade():
    if not _has_table('gen_fixed_period_rules'):
        op.create_table(
            'gen_fixed_period_rules',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id'), index=True),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('description', sa.Text()),
            sa.Column('subject_id', sa.Integer(), sa.ForeignKey('gen_subjects.id'), nullable=False),
            sa.Column('class_name', sa.String(length=20), nullable=False),
            sa.Column('arm_name', sa.String(length=50)),
            sa.Column('fixed_period', sa.Integer(), nullable=False),
            sa.Column('is_active', sa.Boolean(), default=True),
            sa.Column('created_at', sa.DateTime()),
        )


def downgrade():
    if _has_table('gen_fixed_period_rules'):
        op.drop_table('gen_fixed_period_rules')
