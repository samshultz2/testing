"""mock jamb: image_not_needed (admin dismissed a figure-word match)

The needs-images queue now finds every bank question whose wording points at a
picture it doesn't have. ``image_not_needed`` records an admin's "no image
needed" so a false alarm stays out of the queue. Guarded/idempotent.

Revision ID: e5f7a9b1c3d4
Revises: d4e6f8a0b2c3
Create Date: 2026-11-22 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'e5f7a9b1c3d4'
down_revision = 'd4e6f8a0b2c3'
branch_labels = None
depends_on = None


def _has_column(table, column):
    try:
        return column in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return False


def upgrade():
    if not _has_column('mock_jamb_questions', 'image_not_needed'):
        with op.batch_alter_table('mock_jamb_questions', schema=None) as b:
            b.add_column(sa.Column('image_not_needed', sa.Boolean(), nullable=True,
                                   server_default=sa.false()))


def downgrade():
    if _has_column('mock_jamb_questions', 'image_not_needed'):
        with op.batch_alter_table('mock_jamb_questions', schema=None) as b:
            b.drop_column('image_not_needed')
