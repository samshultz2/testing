"""mock jamb online question bank (passages + questions)

Creates ``mock_jamb_passages`` (shared comprehension/cloze/summary/oral stimuli)
and ``mock_jamb_questions`` (objective questions tagged by subject + syllabus
topic/sub-topic, optionally attached to a passage and/or a diagram) for the
in-app Mock JAMB sitting. Idempotent: each table is skipped when already present
(e.g. a dev DB created by create_all).

Revision ID: e0f1a2b3c4d5
Revises: d9e2f3a4b5c6
Create Date: 2026-07-18 12:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'e0f1a2b3c4d5'
down_revision = 'd9e2f3a4b5c6'
branch_labels = None
depends_on = None


def _has_table(name):
    bind = op.get_bind()
    try:
        return name in sa.inspect(bind).get_table_names()
    except Exception:
        return False


def upgrade():
    if not _has_table('mock_jamb_passages'):
        op.create_table(
            'mock_jamb_passages',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('mock_exam_id', sa.Integer(), sa.ForeignKey('mock_jamb_exams.id'), nullable=False),
            sa.Column('subject_id', sa.Integer(), sa.ForeignKey('subjects.id'), nullable=False),
            sa.Column('kind', sa.String(length=20), server_default='comprehension'),
            sa.Column('title', sa.String(length=150)),
            sa.Column('body', sa.Text()),
            sa.Column('image_url', sa.String(length=300)),
            sa.Column('order', sa.Integer(), server_default='0'),
            sa.Column('created_at', sa.DateTime()),
        )
    if not _has_table('mock_jamb_questions'):
        op.create_table(
            'mock_jamb_questions',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('mock_exam_id', sa.Integer(), sa.ForeignKey('mock_jamb_exams.id'), nullable=False),
            sa.Column('subject_id', sa.Integer(), sa.ForeignKey('subjects.id'), nullable=False),
            sa.Column('passage_id', sa.Integer(), sa.ForeignKey('mock_jamb_passages.id'), nullable=True),
            sa.Column('topic', sa.String(length=100)),
            sa.Column('subtopic', sa.String(length=120)),
            sa.Column('question_text', sa.Text(), nullable=False),
            sa.Column('image_url', sa.String(length=300)),
            sa.Column('option_a', sa.String(length=400)),
            sa.Column('option_b', sa.String(length=400)),
            sa.Column('option_c', sa.String(length=400)),
            sa.Column('option_d', sa.String(length=400)),
            sa.Column('correct_option', sa.String(length=1)),
            sa.Column('marks', sa.Float(), server_default='1'),
            sa.Column('order', sa.Integer(), server_default='0'),
            sa.Column('created_at', sa.DateTime()),
        )


def downgrade():
    if _has_table('mock_jamb_questions'):
        op.drop_table('mock_jamb_questions')
    if _has_table('mock_jamb_passages'):
        op.drop_table('mock_jamb_passages')
