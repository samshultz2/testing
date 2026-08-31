"""Perf pass 2: add missing indexes on high-traffic FKs (CONCURRENTLY, non-locking)

Additive only — index creation can never lose data. Built with CREATE INDEX
CONCURRENTLY so a populated production table is not write-locked during the build.
Only indexes NOT already covered by a leftmost unique-constraint column are added
(e.g. student_id on term_results/term_summaries/mock_waec_results is already covered
by their unique constraints).

Revision ID: c4d5e6f7a8b9
Revises: a1b2c3d4e5f6
Create Date: 2026-06-29 00:00:00.000000
"""
from alembic import op


revision = 'c4d5e6f7a8b9'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None

_INDEXES = [
    ('ix_term_result_term', 'term_results', 'term_id'),
    ('ix_term_summary_term', 'term_summaries', 'term_id'),
    ('ix_feepayment_student', 'fee_payments', 'student_id'),
    ('ix_mockwaec_result_exam', 'mock_waec_results', 'mock_exam_id'),
]


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # CONCURRENTLY must run outside a transaction.
        with op.get_context().autocommit_block():
            for name, table, col in _INDEXES:
                op.execute(f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} ({col})')
    else:
        for name, table, col in _INDEXES:
            op.execute(f'CREATE INDEX IF NOT EXISTS {name} ON {table} ({col})')


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        with op.get_context().autocommit_block():
            for name, _table, _col in _INDEXES:
                op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {name}')
    else:
        for name, _table, _col in _INDEXES:
            op.execute(f'DROP INDEX IF EXISTS {name}')
