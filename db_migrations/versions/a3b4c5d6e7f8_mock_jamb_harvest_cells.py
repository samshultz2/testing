"""mock jamb: harvest coverage table (per subject/exam-type/year completeness)

Creates ``mock_jamb_harvest_cells`` so the app can tell whether every ALOC
question for a (subject, exam type, year) has been downloaded. Guarded.

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-07-19 15:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a3b4c5d6e7f8'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on = None


def _has_table(name):
    try:
        return name in sa.inspect(op.get_bind()).get_table_names()
    except Exception:
        return False


def upgrade():
    if _has_table('mock_jamb_harvest_cells'):
        return
    op.create_table(
        'mock_jamb_harvest_cells',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('subject_id', sa.Integer(), sa.ForeignKey('subjects.id'), nullable=False),
        sa.Column('exam_type', sa.String(length=15), server_default='utme'),
        sa.Column('year', sa.String(length=8), nullable=False),
        sa.Column('count', sa.Integer(), server_default='0'),
        sa.Column('complete', sa.Boolean(), server_default=sa.false()),
        sa.Column('updated_at', sa.DateTime()),
        sa.UniqueConstraint('subject_id', 'exam_type', 'year', name='unique_harvest_cell'),
    )


def downgrade():
    if _has_table('mock_jamb_harvest_cells'):
        op.drop_table('mock_jamb_harvest_cells')
