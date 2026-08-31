"""payroll: per-branch runs (payroll_runs.branch_id)

Payroll is per-branch — each branch admin runs their own branch's payroll and a
central admin manages every branch's. Adds branch_id to payroll_runs and makes
the period unique per branch (year, month, branch_id) instead of globally.

Existing rows are left with branch_id = NULL on purpose: a legacy run was
org-wide (it carries payslips for staff across every branch), so it cannot be
attributed to a single branch. The route layer treats NULL-branch runs as
central-only, so branch admins never see other branches' historical payroll.

Revision ID: a2c4e6081357
Revises: f6a7b8c9d0e1
Create Date: 2026-07-05 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a2c4e6081357'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('payroll_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('branch_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_payroll_runs_branch_id', 'branches',
                                    ['branch_id'], ['id'])
        # Period is now unique per branch, so two branches can each have a run
        # for the same month.
        batch_op.drop_constraint('uq_payroll_period', type_='unique')
        batch_op.create_unique_constraint('uq_payroll_period_branch',
                                          ['year', 'month', 'branch_id'])


def downgrade():
    with op.batch_alter_table('payroll_runs', schema=None) as batch_op:
        batch_op.drop_constraint('uq_payroll_period_branch', type_='unique')
        batch_op.create_unique_constraint('uq_payroll_period', ['year', 'month'])
        batch_op.drop_constraint('fk_payroll_runs_branch_id', type_='foreignkey')
        batch_op.drop_column('branch_id')
