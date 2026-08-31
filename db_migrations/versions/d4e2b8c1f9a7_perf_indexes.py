"""performance indexes: class_timetables, student_scores, timetable_backups

Revision ID: d4e2b8c1f9a7
Revises: c3f1a9d2e7b4
Create Date: 2026-06-14 03:20:00.000000

These indexes are also created best-effort at startup by models._ensure_indexes
(CREATE INDEX IF NOT EXISTS); this migration covers Alembic-managed
(SKIP_CREATE_ALL=1) deployments. Uses IF NOT EXISTS so it is safe to re-run and
co-exists with the startup path.
"""
from alembic import op


revision = 'd4e2b8c1f9a7'
down_revision = 'c3f1a9d2e7b4'
branch_labels = None
depends_on = None

_INDEXES = [
    ('ix_classtt_caa', 'class_timetables', 'class_arm_assignment_id'),
    ('ix_classtt_caa_day', 'class_timetables', 'class_arm_assignment_id, day_of_week'),
    ('ix_ttbackup_term', 'timetable_backups', 'term_id'),
    ('ix_score_student', 'student_scores', 'student_id'),
    ('ix_score_classsubject', 'student_scores', 'class_subject_id'),
]


def upgrade():
    for name, table, cols in _INDEXES:
        op.execute(f'CREATE INDEX IF NOT EXISTS {name} ON {table} ({cols})')


def downgrade():
    for name, _table, _cols in _INDEXES:
        op.execute(f'DROP INDEX IF EXISTS {name}')
