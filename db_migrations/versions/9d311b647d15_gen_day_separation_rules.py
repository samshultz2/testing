"""timetable generator: day separation rules

Adds gen_day_separation_rules — keeps a subject off two named days of the
week together, for one class (optionally one specific arm). E.g. SSS1
Rose's Physics can land on Monday or on Friday in a given week, but never
both, without forbidding either day on its own.

Revision ID: 9d311b647d15
Revises: 7a82cd731aad
Create Date: 2026-09-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9d311b647d15'
down_revision = '7a82cd731aad'
branch_labels = None
depends_on = None


def _has_table(table):
    try:
        return table in set(sa.inspect(op.get_bind()).get_table_names())
    except Exception:
        return False


def upgrade():
    if not _has_table('gen_day_separation_rules'):
        op.create_table(
            'gen_day_separation_rules',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id'), index=True),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('description', sa.Text()),
            sa.Column('subject_id', sa.Integer(), sa.ForeignKey('gen_subjects.id'), nullable=False),
            sa.Column('class_name', sa.String(length=20), nullable=False),
            sa.Column('arm_name', sa.String(length=50)),
            sa.Column('day_a', sa.Integer(), nullable=False),
            sa.Column('day_b', sa.Integer(), nullable=False),
            sa.Column('is_active', sa.Boolean(), default=True),
            sa.Column('created_at', sa.DateTime()),
        )


def downgrade():
    if _has_table('gen_day_separation_rules'):
        op.drop_table('gen_day_separation_rules')
