"""timetable generator: per-class subject period restrictions

Adds not_first_period/not_last_period/avoid_morning/avoid_afternoon/
excluded_periods to gen_class_subject_configs — until now, "don't schedule
this subject first/last/in the morning/afternoon/in a specific period" could
only be set globally per subject (GenSubjectConfig, school-level-wide), with
one hardcoded exception (Mathematics not-first for SSS1-3) baked into the
solver itself. This makes it a real per-class setting, and the hardcoded
exception is removed in the same change (routes/generator_ortools.py) since
schools can now set it themselves where it actually applies.

Revision ID: d1e2f3a4b5c6
Revises: b3c4d5e6f7a8
Create Date: 2026-09-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd1e2f3a4b5c6'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


def _has_column(table, column):
    try:
        return column in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return False


_NEW_COLUMNS = [
    ('not_first_period', sa.Boolean(), sa.false()),
    ('not_last_period', sa.Boolean(), sa.false()),
    ('avoid_morning', sa.Boolean(), sa.false()),
    ('avoid_afternoon', sa.Boolean(), sa.false()),
    ('excluded_periods', sa.String(length=50), None),
]


def upgrade():
    for name, col_type, default in _NEW_COLUMNS:
        if not _has_column('gen_class_subject_configs', name):
            with op.batch_alter_table('gen_class_subject_configs', schema=None) as b:
                if default is not None:
                    b.add_column(sa.Column(name, col_type, server_default=default))
                else:
                    b.add_column(sa.Column(name, col_type))


def downgrade():
    for name, _, _ in reversed(_NEW_COLUMNS):
        if _has_column('gen_class_subject_configs', name):
            with op.batch_alter_table('gen_class_subject_configs', schema=None) as b:
                b.drop_column(name)
