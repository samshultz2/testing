"""study groups: group_sets, student_groups, group_members

Tools -> Study/Project Groups: group a class's students for group work,
ranked by their average score the term before (carrying over from the
previous session's last term when the current term is a session's first),
with the strongest performers made group leaders. Its own tables, never
touching ClassArmAssignment/StudentEnrollment -- "merge two arms" here only
widens this tool's candidate pool, never enrollment itself.

Revision ID: ac9d0db57202
Revises: d2344608db64
Create Date: 2026-10-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'ac9d0db57202'
down_revision = 'd2344608db64'
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(table):
    return table in set(_insp().get_table_names())


def upgrade():
    if not _has_table('group_sets'):
        op.create_table(
            'group_sets',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id')),
            sa.Column('class_id', sa.Integer(), sa.ForeignKey('school_classes.id'), nullable=False),
            sa.Column('arm_ids', sa.String(length=200), nullable=False),
            sa.Column('term_id', sa.Integer(), sa.ForeignKey('terms.id'), nullable=False),
            sa.Column('basis_term_id', sa.Integer(), sa.ForeignKey('terms.id')),
            sa.Column('group_size', sa.Integer(), nullable=False),
            sa.Column('num_groups', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(length=150)),
            sa.Column('created_by', sa.String(length=100)),
            sa.Column('created_at', sa.DateTime()),
        )
    if not _has_table('student_groups'):
        op.create_table(
            'student_groups',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('group_set_id', sa.Integer(), sa.ForeignKey('group_sets.id'),
                      nullable=False, index=True),
            sa.Column('position', sa.Integer(), nullable=False),
            sa.Column('label', sa.String(length=80)),
            sa.Column('leader_student_id', sa.Integer(), sa.ForeignKey('students.id')),
        )
    if not _has_table('group_members'):
        op.create_table(
            'group_members',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('group_set_id', sa.Integer(), sa.ForeignKey('group_sets.id'),
                      nullable=False, index=True),
            sa.Column('group_id', sa.Integer(), sa.ForeignKey('student_groups.id'),
                      nullable=False, index=True),
            sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id'), nullable=False),
            sa.Column('basis_average', sa.Float()),
            sa.UniqueConstraint('group_set_id', 'student_id', name='uq_group_member_once_per_set'),
        )


def downgrade():
    for table in ('group_members', 'student_groups', 'group_sets'):
        if _has_table(table):
            op.drop_table(table)
