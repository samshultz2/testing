"""add gen_class_configs.require_free_first_period

Per-class toggle for the timetable generator: when on, any day this class
(-arm) ends up with at least one free period, period 1 must be one of them
-- enforced by the solver as a hard constraint. Days that come out fully
packed are unaffected. Off by default, matching every other per-class
scheduling toggle in this app.

Revision ID: e2f3a4b5c6d7
Revises: d4e5f6a7b8c9
Create Date: 2026-09-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e2f3a4b5c6d7'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def _has_column(table, column):
    bind = op.get_bind()
    return column in {c['name'] for c in sa.inspect(bind).get_columns(table)}


def upgrade():
    if not _has_column('gen_class_configs', 'require_free_first_period'):
        op.add_column('gen_class_configs',
                      sa.Column('require_free_first_period', sa.Boolean(), nullable=True))


def downgrade():
    if _has_column('gen_class_configs', 'require_free_first_period'):
        op.drop_column('gen_class_configs', 'require_free_first_period')
