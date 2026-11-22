"""exam_timetables — WAEC / NECO exam timetables and their papers

Revision ID: b2c4d6e8f0a1
Revises: a1b3c5d7e9f2
Create Date: 2026-11-22 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b2c4d6e8f0a1'
down_revision = 'a1b3c5d7e9f2'
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    if not insp.has_table('exam_timetables'):
        op.create_table(
            'exam_timetables',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id')),
            sa.Column('board', sa.String(10), nullable=False, server_default='waec'),
            sa.Column('title', sa.String(150), nullable=False),
            sa.Column('year', sa.Integer()),
            sa.Column('notes', sa.Text()),
            sa.Column('created_by', sa.String(100)),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('updated_at', sa.DateTime()),
        )
        op.create_index('ix_exam_timetables_branch_id', 'exam_timetables', ['branch_id'])
    if not insp.has_table('exam_timetable_papers'):
        op.create_table(
            'exam_timetable_papers',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('timetable_id', sa.Integer(),
                      sa.ForeignKey('exam_timetables.id', ondelete='CASCADE'), nullable=False),
            sa.Column('exam_date', sa.Date(), nullable=False),
            sa.Column('start_time', sa.Time(), nullable=False),
            sa.Column('end_time', sa.Time(), nullable=False),
            sa.Column('subject', sa.String(120), nullable=False),
            sa.Column('paper', sa.String(120)),
            sa.Column('kind', sa.String(20)),
            sa.Column('venue', sa.String(120)),
            sa.Column('invigilators', sa.String(255)),
            sa.Column('notes', sa.String(255)),
        )
        op.create_index('ix_exam_timetable_papers_timetable_id', 'exam_timetable_papers', ['timetable_id'])


def downgrade():
    insp = sa.inspect(op.get_bind())
    if insp.has_table('exam_timetable_papers'):
        op.drop_index('ix_exam_timetable_papers_timetable_id', table_name='exam_timetable_papers')
        op.drop_table('exam_timetable_papers')
    if insp.has_table('exam_timetables'):
        op.drop_index('ix_exam_timetables_branch_id', table_name='exam_timetables')
        op.drop_table('exam_timetables')
