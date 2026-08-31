"""add students.waec_epin (WAEC e-PIN)

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-08-08 05:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f8a9b0c1d2e3'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def _has_column(table, column):
    bind = op.get_bind()
    return column in {c['name'] for c in sa.inspect(bind).get_columns(table)}


def upgrade():
    if not _has_column('students', 'waec_epin'):
        op.add_column('students', sa.Column('waec_epin', sa.String(length=30), nullable=True))


def downgrade():
    if _has_column('students', 'waec_epin'):
        op.drop_column('students', 'waec_epin')
