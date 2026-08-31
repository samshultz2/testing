"""mock JAMB exam: per-branch ownership + scoped uniqueness

Adds branch_id to mock_jamb_exams so a mock exam belongs to a branch (enabling
branch-scoped access control), backfills existing exams to the default branch
so they aren't left world-readable, and makes the (session, exam_number)
uniqueness per-branch.

Revision ID: e7f3a9b2c1d8
Revises: d4e2b8c1f9a7
Create Date: 2026-06-15 04:40:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7f3a9b2c1d8'
down_revision = 'd4e2b8c1f9a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('mock_jamb_exams', schema=None) as batch_op:
        batch_op.add_column(sa.Column('branch_id', sa.Integer(), nullable=True))
        batch_op.drop_constraint('unique_mock_exam_per_session', type_='unique')
        batch_op.create_unique_constraint(
            'unique_mock_exam_per_session', ['session_id', 'exam_number', 'branch_id'])
        batch_op.create_foreign_key(
            'fk_mock_jamb_exams_branch_id', 'branches', ['branch_id'], ['id'])

    # Backfill existing (unbranched) exams to the default branch, falling back
    # to the lowest branch id — otherwise can_access_branch(None) would leave
    # them readable by everyone.
    op.execute(
        "UPDATE mock_jamb_exams SET branch_id = "
        "(SELECT id FROM branches WHERE is_default = 1 ORDER BY id LIMIT 1) "
        "WHERE branch_id IS NULL"
    )
    op.execute(
        "UPDATE mock_jamb_exams SET branch_id = (SELECT MIN(id) FROM branches) "
        "WHERE branch_id IS NULL"
    )


def downgrade():
    with op.batch_alter_table('mock_jamb_exams', schema=None) as batch_op:
        batch_op.drop_constraint('fk_mock_jamb_exams_branch_id', type_='foreignkey')
        batch_op.drop_constraint('unique_mock_exam_per_session', type_='unique')
        batch_op.create_unique_constraint(
            'unique_mock_exam_per_session', ['session_id', 'exam_number'])
        batch_op.drop_column('branch_id')
