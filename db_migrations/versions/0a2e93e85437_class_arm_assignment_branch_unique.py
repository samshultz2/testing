"""class_arm_assignments: make the unique constraint per-branch

Same class of bug as a2c4e6081357 (payroll_runs): the unique constraint on
(class_id, arm_id, term_id) didn't include branch_id, so only the FIRST
branch to set up e.g. 'JSS1 Rose' for a term could ever have one — every
other branch's attempt to create their own hit a duplicate-key error at the
database level, no matter what the application code did. This is what made
it look like all data "belonged to" the default branch: other branches were
silently unable to create their own assignments at all.

class_id/arm_id/term_id/branch_id together is the correct uniqueness — each
branch can now have its own 'JSS1 Rose' for the same term. branch_id stays
nullable (a legacy single-branch install may have rows with no branch_id
set at all); SQL treats multiple NULLs in a unique constraint as distinct,
so that's compatible with this change, not a special case to migrate.

No existing data can violate the new (broader) constraint — it only adds
allowed combinations relative to the old one, so no cleanup is needed
before applying it.

Revision ID: 0a2e93e85437
Revises: 53bce1b78153
Create Date: 2026-09-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0a2e93e85437'
down_revision = '53bce1b78153'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('class_arm_assignments', schema=None) as batch_op:
        batch_op.drop_constraint('unique_class_arm_term', type_='unique')
        batch_op.create_unique_constraint(
            'unique_class_arm_term_branch', ['class_id', 'arm_id', 'term_id', 'branch_id'])


def downgrade():
    with op.batch_alter_table('class_arm_assignments', schema=None) as batch_op:
        batch_op.drop_constraint('unique_class_arm_term_branch', type_='unique')
        batch_op.create_unique_constraint(
            'unique_class_arm_term', ['class_id', 'arm_id', 'term_id'])
