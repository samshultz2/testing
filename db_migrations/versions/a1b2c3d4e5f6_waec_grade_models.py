"""WAEC grade-band prediction: trained per-(branch, subject) model store

Adds the waec_grade_models table that persists the fitted proportional-odds
ordinal model (parameters as JSON) plus its metadata (training pair count and
cross-validated Ranked Probability Score for the model vs the calibration bins),
one row per branch+subject, re-fit whenever a new cohort's real WAEC results land.

Revision ID: a1b2c3d4e5f6
Revises: b2f4a6c8e012
Create Date: 2026-06-28 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'b2f4a6c8e012'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'waec_grade_models',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=True),
        sa.Column('subject', sa.String(length=50), nullable=False),
        sa.Column('params', sa.Text(), nullable=False),
        sa.Column('n', sa.Integer(), nullable=True),
        sa.Column('cv_rps', sa.Float(), nullable=True),
        sa.Column('cv_rps_bins', sa.Float(), nullable=True),
        sa.Column('trained_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('branch_id', 'subject', name='unique_waec_model_branch_subject'),
    )


def downgrade():
    op.drop_table('waec_grade_models')
