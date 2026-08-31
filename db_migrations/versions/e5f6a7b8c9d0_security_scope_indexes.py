"""security & branch-scope indexes: monitoring + branch_id access-control filter

Revision ID: e5f6a7b8c9d0
Revises: c4d5e6f7a8b9
Create Date: 2026-07-02 09:00:00.000000

Parity migration for the DB-access audit. These indexes are also created
best-effort at startup by models._ensure_indexes (CREATE INDEX IF NOT EXISTS);
this migration covers Alembic-managed (SKIP_CREATE_ALL=1) deployments so the
audit viewer, the login throttle, and every branch-scoped list are indexed even
when the startup helper is skipped. Uses IF NOT EXISTS so it is safe to re-run
and co-exists with the startup path.
"""
from alembic import op


revision = 'e5f6a7b8c9d0'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None

_INDEXES = [
    # Security monitoring: audit trail + login rate-limit / lockout lookups.
    ('ix_audit_created', 'audit_logs', 'created_at'),
    ('ix_audit_action', 'audit_logs', 'action'),
    ('ix_ratelimit_key_ts', 'rate_limit_hits', 'rkey, ts'),
    # branch_id — the primary access-control filter on branch-owned tables.
    ('ix_user_branch', 'users', 'branch_id'),
    ('ix_teacher_branch', 'teachers', 'branch_id'),
    ('ix_staff_branch', 'staff_members', 'branch_id'),
    ('ix_cbtexam_branch', 'cbt_exams', 'branch_id'),
    ('ix_book_branch', 'library_books', 'branch_id'),
    ('ix_applicant_branch', 'applicants', 'branch_id'),
    ('ix_message_branch', 'messages', 'branch_id'),
    ('ix_permgroup_branch', 'permission_groups', 'branch_id'),
    ('ix_mockjamb_exam_branch', 'mock_jamb_exams', 'branch_id'),
    ('ix_mockwaec_exam_branch', 'mock_waec_exams', 'branch_id'),
]


def upgrade():
    for name, table, cols in _INDEXES:
        op.execute(f'CREATE INDEX IF NOT EXISTS {name} ON {table} ({cols})')


def downgrade():
    for name, _table, _cols in _INDEXES:
        op.execute(f'DROP INDEX IF EXISTS {name}')
