"""branch grade distributions: whole-class summary sheets for branches that
don't enter per-student WAEC/JAMB results

Revision ID: 7a82cd731aad
Revises: 7a99ffe8e3f4
Create Date: 2026-09-19 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7a82cd731aad'
down_revision = '7a99ffe8e3f4'
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(table):
    return table in set(_insp().get_table_names())


def upgrade():
    if not _has_table('branch_grade_distributions'):
        op.create_table(
            'branch_grade_distributions',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id'), nullable=False, index=True),
            sa.Column('exam', sa.String(length=12), nullable=False),
            sa.Column('exam_year', sa.Integer()),
            sa.Column('mock_session_id', sa.Integer(), sa.ForeignKey('academic_sessions.id')),
            sa.Column('mock_exam_number', sa.Integer()),
            sa.Column('subject', sa.String(length=60), nullable=False),
            sa.Column('candidates', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('band_counts', sa.Text(), nullable=False, server_default='{}'),
            sa.Column('source', sa.String(length=10)),
            sa.Column('imported_by', sa.Integer(), sa.ForeignKey('users.id')),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('updated_at', sa.DateTime()),
        )
        op.create_index('ix_branch_grade_dist_lookup', 'branch_grade_distributions',
                        ['branch_id', 'exam', 'exam_year', 'mock_session_id', 'mock_exam_number'])


def downgrade():
    if _has_table('branch_grade_distributions'):
        op.drop_table('branch_grade_distributions')
