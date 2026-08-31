"""mock jamb: needs_image (figure-dependent questions held out of exams)

Adds ``needs_image`` to ``mock_jamb_questions`` — True when a scraped question
refers to a figure we couldn't fetch, so it is excluded from the draw until an
admin uploads the image via the "needs images" review queue. Guarded/idempotent.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-07-23 17:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'd6e7f8a9b0c1'
down_revision = 'c5d6e7f8a9b0'
branch_labels = None
depends_on = None


def _has_column(table, column):
    try:
        return column in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return False


def upgrade():
    if not _has_column('mock_jamb_questions', 'needs_image'):
        with op.batch_alter_table('mock_jamb_questions', schema=None) as b:
            b.add_column(sa.Column('needs_image', sa.Boolean(), nullable=True,
                                   server_default=sa.false()))


def downgrade():
    pass
