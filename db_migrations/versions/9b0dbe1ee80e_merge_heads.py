"""merge heads: active_timetable_batches + the co-schedule-rules/purge-fix line

Two migration heads forked independently and were never reconciled:
b2f4a6c8e012 (active_timetable_batches) and 9b4ba1e5aebe (chained off
f00dc0e5c001 gen_co_schedule_rules, itself extended by the student-purge
nullability fix). This is a pure graph merge — no schema changes — so
`alembic upgrade head` / `flask db upgrade` has a single unambiguous target
again.

Revision ID: 9b0dbe1ee80e
Revises: b2f4a6c8e012, 9b4ba1e5aebe
Create Date: 2026-09-15 06:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '9b0dbe1ee80e'
down_revision = ('b2f4a6c8e012', '9b4ba1e5aebe')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
