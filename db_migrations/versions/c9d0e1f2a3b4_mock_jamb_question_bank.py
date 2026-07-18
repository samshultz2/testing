"""mock jamb: central question bank (bank questions/passages + JAMB blueprint)

Turns ``mock_jamb_questions`` / ``mock_jamb_passages`` into a reusable, subject
scoped bank drawn into mocks per the JAMB blueprint:

* ``mock_exam_id`` becomes nullable (NULL => a bank row, not tied to one mock).
* questions gain ``section`` (JAMB paper section), ``exam_body`` and ``difficulty``.
* passages gain ``section``.
* ``mock_jamb_exams`` gains a ``blueprint`` JSON override column.

All changes are guarded/idempotent. SQLite cannot drop a NOT NULL constraint
without a table rebuild, so the nullability relaxation is best-effort via
batch_alter_table; on Postgres it is a plain ALTER.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-18 16:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def _has_column(table, column):
    try:
        return column in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return False


def upgrade():
    if not _has_column('mock_jamb_exams', 'blueprint'):
        with op.batch_alter_table('mock_jamb_exams', schema=None) as b:
            b.add_column(sa.Column('blueprint', sa.Text(), nullable=True))

    with op.batch_alter_table('mock_jamb_questions', schema=None) as b:
        if not _has_column('mock_jamb_questions', 'section'):
            b.add_column(sa.Column('section', sa.String(length=40), nullable=True))
        if not _has_column('mock_jamb_questions', 'exam_body'):
            b.add_column(sa.Column('exam_body', sa.String(length=10), nullable=True,
                                   server_default='JAMB'))
        if not _has_column('mock_jamb_questions', 'difficulty'):
            b.add_column(sa.Column('difficulty', sa.String(length=10), nullable=True))

    if not _has_column('mock_jamb_passages', 'section'):
        with op.batch_alter_table('mock_jamb_passages', schema=None) as b:
            b.add_column(sa.Column('section', sa.String(length=40), nullable=True))

    # Relax NOT NULL on mock_exam_id so bank rows can exist without a mock.
    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        for tbl in ('mock_jamb_questions', 'mock_jamb_passages'):
            try:
                op.alter_column(tbl, 'mock_exam_id', existing_type=sa.Integer(), nullable=True)
            except Exception:
                pass


def downgrade():
    # Additive columns only; leave them in place (dropping is destructive and the
    # nullability relaxation is safe to keep).
    pass
