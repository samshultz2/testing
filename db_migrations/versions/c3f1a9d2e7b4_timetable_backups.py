"""timetable_backups table

Revision ID: c3f1a9d2e7b4
Revises: 1f380f8f3bf5
Create Date: 2026-06-13 18:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3f1a9d2e7b4'
down_revision = '1f380f8f3bf5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'timetable_backups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('term_id', sa.Integer(), nullable=True),
        sa.Column('label', sa.String(length=200), nullable=True),
        sa.Column('entry_count', sa.Integer(), nullable=True),
        sa.Column('data', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['term_id'], ['terms.id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('timetable_backups')
