"""syllabus topics/sub-topics + question sub-topic tags

Creates ``syllabus_topics`` (a subject's WAEC/JAMB curriculum topics, with
sub-topics via ``parent_id``) and adds a nullable ``subtopic`` column to
``cbt_questions`` and ``question_bank`` so authored questions can be tagged to a
sub-topic. Idempotent: each change is skipped when already present (e.g. a dev
DB created by create_all).

Revision ID: d9e2f3a4b5c6
Revises: c8a1b2d3e4f5
Create Date: 2026-07-18 11:40:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'd9e2f3a4b5c6'
down_revision = 'c8a1b2d3e4f5'
branch_labels = None
depends_on = None


def _has_table(name):
    bind = op.get_bind()
    try:
        return name in sa.inspect(bind).get_table_names()
    except Exception:
        return False


def _has_column(table, column):
    bind = op.get_bind()
    try:
        return column in {c['name'] for c in sa.inspect(bind).get_columns(table)}
    except Exception:
        return False


def upgrade():
    if not _has_table('syllabus_topics'):
        op.create_table(
            'syllabus_topics',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('subject_id', sa.Integer(), sa.ForeignKey('subjects.id'), nullable=False),
            sa.Column('parent_id', sa.Integer(), sa.ForeignKey('syllabus_topics.id'), nullable=True),
            sa.Column('title', sa.String(length=120), nullable=False),
            sa.Column('exam_body', sa.String(length=10), server_default='Both'),
            sa.Column('order', sa.Integer(), server_default='0'),
            sa.Column('is_active', sa.Boolean(), server_default=sa.true()),
            sa.Column('created_at', sa.DateTime()),
            sa.UniqueConstraint('subject_id', 'parent_id', 'title', name='uq_syllabus_topic'),
        )
    if not _has_column('cbt_questions', 'subtopic'):
        with op.batch_alter_table('cbt_questions', schema=None) as batch_op:
            batch_op.add_column(sa.Column('subtopic', sa.String(length=120), nullable=True))
    if not _has_column('question_bank', 'subtopic'):
        with op.batch_alter_table('question_bank', schema=None) as batch_op:
            batch_op.add_column(sa.Column('subtopic', sa.String(length=120), nullable=True))


def downgrade():
    if _has_column('question_bank', 'subtopic'):
        with op.batch_alter_table('question_bank', schema=None) as batch_op:
            batch_op.drop_column('subtopic')
    if _has_column('cbt_questions', 'subtopic'):
        with op.batch_alter_table('cbt_questions', schema=None) as batch_op:
            batch_op.drop_column('subtopic')
    if _has_table('syllabus_topics'):
        op.drop_table('syllabus_topics')
