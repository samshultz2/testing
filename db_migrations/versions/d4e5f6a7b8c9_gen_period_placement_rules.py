"""timetable generator: generalize fixed-period rules into period-placement rules

Replaces gen_fixed_period_rules (pin-to-one-period only) with
gen_period_placement_rules, which adds not_first / not_last / morning_only /
afternoon_only / range alongside the original fixed-period pin, all scoped
to one class (optionally one arm) the same way as before.

gen_fixed_period_rules never successfully existed on any deployed database
(the prior migration adding it had not yet been run anywhere when this one
was written), so there is no real data to migrate -- this simply drops it
if present and creates the new table fresh.

Revision ID: d4e5f6a7b8c9
Revises: b7c8d9e0f1a2
Create Date: 2026-09-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b8c9'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None


def _has_table(table):
    try:
        return table in set(sa.inspect(op.get_bind()).get_table_names())
    except Exception:
        return False


def upgrade():
    if _has_table('gen_fixed_period_rules'):
        op.drop_table('gen_fixed_period_rules')

    if not _has_table('gen_period_placement_rules'):
        op.create_table(
            'gen_period_placement_rules',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id'), index=True),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('description', sa.Text()),
            sa.Column('subject_id', sa.Integer(), sa.ForeignKey('gen_subjects.id'), nullable=False),
            sa.Column('class_name', sa.String(length=20), nullable=False),
            sa.Column('arm_name', sa.String(length=50)),
            sa.Column('rule_type', sa.String(length=20), nullable=False, server_default='fixed'),
            sa.Column('period_value', sa.Integer()),
            sa.Column('range_end', sa.Integer()),
            sa.Column('is_active', sa.Boolean(), default=True),
            sa.Column('created_at', sa.DateTime()),
        )


def downgrade():
    if _has_table('gen_period_placement_rules'):
        op.drop_table('gen_period_placement_rules')

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
