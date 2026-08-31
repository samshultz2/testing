"""cbt: syllabus-topic tag on questions (cbt_questions.topic)

Adds a nullable ``topic`` column to ``cbt_questions`` so objective questions can
be tagged with a syllabus topic, powering the topic-mastery analytics
(per-exam, per-student and subject-level). Idempotent: skipped when the column
already exists (e.g. a dev DB created by create_all).

Revision ID: c8a1b2d3e4f5
Revises: b3d5f7092468
Create Date: 2026-07-18 05:20:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'c8a1b2d3e4f5'
down_revision = 'b3d5f7092468'
branch_labels = None
depends_on = None


def _has_column(table, column):
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return column in {c['name'] for c in insp.get_columns(table)}
    except Exception:
        return False


def upgrade():
    if not _has_column('cbt_questions', 'topic'):
        with op.batch_alter_table('cbt_questions', schema=None) as batch_op:
            batch_op.add_column(sa.Column('topic', sa.String(length=100), nullable=True))


def downgrade():
    if _has_column('cbt_questions', 'topic'):
        with op.batch_alter_table('cbt_questions', schema=None) as batch_op:
            batch_op.drop_column('topic')
