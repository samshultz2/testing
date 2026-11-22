"""exam timetable papers: Mathematics -> General Mathematics

Revision ID: d4e6f8a0b2c3
Revises: c3d5e7f9a1b2
Create Date: 2026-11-22 13:00:00.000000

WAEC and NECO both print the subject as "General Mathematics"; rename papers
saved as plain "Mathematics" (or Maths) so the printed timetable matches.
"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e6f8a0b2c3'
down_revision = 'c3d5e7f9a1b2'
branch_labels = None
depends_on = None


def upgrade():
    if sa.inspect(op.get_bind()).has_table('exam_timetable_papers'):
        op.execute("UPDATE exam_timetable_papers SET subject = 'General Mathematics' "
                   "WHERE lower(trim(subject)) IN ('mathematics', 'maths', 'math', 'general maths')")


def downgrade():
    pass
