"""mock jamb online sitting — attempts + answers, publish + duration

Adds ``is_published`` and ``duration_minutes`` to ``mock_jamb_exams`` and creates
``mock_jamb_attempts`` and ``mock_jamb_answers`` for the in-app Mock JAMB sitting.
Idempotent: each change is skipped when already present.

Revision ID: a7b8c9d0e1f2
Revises: e0f1a2b3c4d5
Create Date: 2026-07-18 13:20:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a7b8c9d0e1f2'
down_revision = 'e0f1a2b3c4d5'
branch_labels = None
depends_on = None


def _has_table(name):
    try:
        return name in sa.inspect(op.get_bind()).get_table_names()
    except Exception:
        return False


def _has_column(table, column):
    try:
        return column in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return False


def upgrade():
    if not _has_column('mock_jamb_exams', 'is_published'):
        with op.batch_alter_table('mock_jamb_exams', schema=None) as b:
            b.add_column(sa.Column('is_published', sa.Boolean(), server_default=sa.false()))
    if not _has_column('mock_jamb_exams', 'duration_minutes'):
        with op.batch_alter_table('mock_jamb_exams', schema=None) as b:
            b.add_column(sa.Column('duration_minutes', sa.Integer(), server_default='120'))
    if not _has_table('mock_jamb_attempts'):
        op.create_table(
            'mock_jamb_attempts',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('mock_exam_id', sa.Integer(), sa.ForeignKey('mock_jamb_exams.id'), nullable=False),
            sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id'), nullable=False),
            sa.Column('started_at', sa.DateTime()),
            sa.Column('submitted_at', sa.DateTime()),
            sa.Column('status', sa.String(length=15), server_default='In progress'),
            sa.Column('total_score', sa.Integer(), server_default='0'),
            sa.Column('duration_minutes', sa.Integer(), server_default='120'),
            sa.Column('created_at', sa.DateTime()),
            sa.UniqueConstraint('mock_exam_id', 'student_id', name='unique_mock_attempt'),
        )
    if not _has_table('mock_jamb_answers'):
        op.create_table(
            'mock_jamb_answers',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('attempt_id', sa.Integer(), sa.ForeignKey('mock_jamb_attempts.id'), nullable=False),
            sa.Column('question_id', sa.Integer(), sa.ForeignKey('mock_jamb_questions.id'), nullable=False),
            sa.Column('selected_option', sa.String(length=1)),
            sa.Column('is_correct', sa.Boolean(), server_default=sa.false()),
            sa.UniqueConstraint('attempt_id', 'question_id', name='unique_mock_answer'),
        )


def downgrade():
    if _has_table('mock_jamb_answers'):
        op.drop_table('mock_jamb_answers')
    if _has_table('mock_jamb_attempts'):
        op.drop_table('mock_jamb_attempts')
    for col in ('duration_minutes', 'is_published'):
        if _has_column('mock_jamb_exams', col):
            with op.batch_alter_table('mock_jamb_exams', schema=None) as b:
                b.drop_column(col)
