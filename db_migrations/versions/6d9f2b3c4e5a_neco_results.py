"""NECO results table + students.neco_reg_number / neco_epin

Revision ID: 6d9f2b3c4e5a
Revises: 5c8e1a2b3d4f
Create Date: 2026-11-06 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '6d9f2b3c4e5a'
down_revision = '5c8e1a2b3d4f'
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_column(table, column):
    return column in {c['name'] for c in _insp().get_columns(table)}


def upgrade():
    if not _insp().has_table('neco_results'):
        op.create_table(
            'neco_results',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id'), nullable=False),
            sa.Column('exam_year', sa.Integer(), nullable=False),
            sa.Column('subject', sa.String(length=50), nullable=False),
            sa.Column('grade', sa.String(length=2), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.UniqueConstraint('student_id', 'exam_year', 'subject', name='unique_neco_result'),
        )
    for col in ('neco_reg_number', 'neco_epin'):
        if not _has_column('students', col):
            op.add_column('students', sa.Column(col, sa.String(length=30), nullable=True))
    if 'ix_students_neco_reg_number' not in {i['name'] for i in _insp().get_indexes('students')}:
        op.create_index('ix_students_neco_reg_number', 'students', ['neco_reg_number'])


def downgrade():
    for col in ('neco_epin', 'neco_reg_number'):
        if _has_column('students', col):
            op.drop_column('students', col)
    if _insp().has_table('neco_results'):
        op.drop_table('neco_results')
