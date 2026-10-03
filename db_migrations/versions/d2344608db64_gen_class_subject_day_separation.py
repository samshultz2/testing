"""add gen_class_subject_configs.day_separation_exempt

Per-class override for the school-wide day-separation default (whether a
subject is kept off two named days together) -- the subject-level default
(GenSubjectConfig.day_separation_exempt) picks whether a subject is in the
rule at all; this lets one class opt OUT of (or back INTO) that choice
without changing it for every other class taking the subject.

Nullable, unlike most other per-class overrides here: a GenClassSubjectConfig
row already exists for nearly every (class, subject) pair just from
periods_per_week, so "row exists" can't mean "this class has an explicit
day-separation preference" the way it does for e.g. is_enabled. NULL means
"no override, inherit the subject-level default"; True/False is an explicit
per-class choice either direction.

Revision ID: d2344608db64
Revises: e2f3a4b5c6d7
Create Date: 2026-10-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd2344608db64'
down_revision = 'e2f3a4b5c6d7'
branch_labels = None
depends_on = None


def _has_column(table, column):
    bind = op.get_bind()
    return column in {c['name'] for c in sa.inspect(bind).get_columns(table)}


def upgrade():
    if not _has_column('gen_class_subject_configs', 'day_separation_exempt'):
        op.add_column('gen_class_subject_configs',
                      sa.Column('day_separation_exempt', sa.Boolean(), nullable=True))


def downgrade():
    if _has_column('gen_class_subject_configs', 'day_separation_exempt'):
        op.drop_column('gen_class_subject_configs', 'day_separation_exempt')
