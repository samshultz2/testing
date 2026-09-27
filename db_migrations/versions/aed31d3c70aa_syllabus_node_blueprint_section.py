"""mock jamb syllabus nodes: blueprint_section

Ties the coded syllabus tree to the flat draw blueprint's section field, so a
confident coded classification (utils.mock_bank_coded_retag) can also set the
question's `section` correctly instead of leaving it to the separate,
weaker keyword classifier. NULL until curated per node. Guarded/idempotent.

Revision ID: aed31d3c70aa
Revises: 43ad04986b11
Create Date: 2026-09-27 05:10:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'aed31d3c70aa'
down_revision = '43ad04986b11'
branch_labels = None
depends_on = None


def _has_column(table, column):
    try:
        return column in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return False


def upgrade():
    if not _has_column('mock_jamb_syllabus_nodes', 'blueprint_section'):
        with op.batch_alter_table('mock_jamb_syllabus_nodes', schema=None) as b:
            b.add_column(sa.Column('blueprint_section', sa.String(length=40), nullable=True))


def downgrade():
    pass
