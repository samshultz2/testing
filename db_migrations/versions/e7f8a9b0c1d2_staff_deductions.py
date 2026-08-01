"""per-staff recurring deduction amounts

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-08-01 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7f8a9b0c1d2'
down_revision = 'd6e7f8a9b0c1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('staff_deductions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('staff_id', sa.Integer(), nullable=False),
    sa.Column('deduction_type_id', sa.Integer(), nullable=False),
    sa.Column('amount', sa.Float(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['staff_id'], ['staff_members.id'], ),
    sa.ForeignKeyConstraint(['deduction_type_id'], ['payroll_deduction_types.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('staff_id', 'deduction_type_id', name='uq_staff_deduction')
    )


def downgrade():
    op.drop_table('staff_deductions')
