"""timetable generator: co-schedule rules

Adds gen_co_schedule_rules — pairs two subjects (usually from different arms
of a combined class, e.g. SSS2 Daisy's Literature with SSS2 Iris's
Accounting) so the solver forces them into the exact same time slot every
occurrence, instead of just avoiding a clash between them.

Revision ID: f00dc0e5c001
Revises: dadecafed006
Create Date: 2026-09-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f00dc0e5c001'
down_revision = 'dadecafed006'
branch_labels = None
depends_on = None


def _has_table(table):
    try:
        return table in set(sa.inspect(op.get_bind()).get_table_names())
    except Exception:
        return False


def upgrade():
    if not _has_table('gen_co_schedule_rules'):
        op.create_table(
            'gen_co_schedule_rules',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id'), index=True),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('description', sa.Text()),
            sa.Column('source_subject_id', sa.Integer(), sa.ForeignKey('gen_subjects.id'), nullable=False),
            sa.Column('source_class_name', sa.String(length=20), nullable=False),
            sa.Column('source_arm_name', sa.String(length=50), nullable=False),
            sa.Column('target_subject_id', sa.Integer(), sa.ForeignKey('gen_subjects.id'), nullable=False),
            sa.Column('target_class_name', sa.String(length=20), nullable=False),
            sa.Column('target_arm_name', sa.String(length=50), nullable=False),
            sa.Column('is_active', sa.Boolean(), default=True),
            sa.Column('created_at', sa.DateTime()),
        )


def downgrade():
    if _has_table('gen_co_schedule_rules'):
        op.drop_table('gen_co_schedule_rules')
