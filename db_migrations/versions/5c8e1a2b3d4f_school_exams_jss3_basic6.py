"""JSS3 (BECE) and Basic 6 (Common Entrance) external exams

Adds three tables shared by the two separate level modules (keyed by
``level`` = jss3 / basic6 and ``body`` = state / federal):

* school_exam_configs    — per (level, body) exam name, subjects, grade bands,
                           max score, benchmark and admission cut-off
* school_exam_results    — one subject result (score and/or grade) per candidate
* school_exam_candidates — per-candidate sitting: exam number, centre, total,
                           placement / admission outcome

Fully guarded/idempotent, matching the self-heal in utils/school_exams.py.

Revision ID: 5c8e1a2b3d4f
Revises: fe0d92ec9a80
Create Date: 2026-11-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '5c8e1a2b3d4f'
down_revision = 'fe0d92ec9a80'
branch_labels = None
depends_on = None


def _has_table(table):
    return table in set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    if not _has_table('school_exam_configs'):
        op.create_table(
            'school_exam_configs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('level', sa.String(length=10), nullable=False),
            sa.Column('body', sa.String(length=10), nullable=False),
            sa.Column('exam_name', sa.String(length=120)),
            sa.Column('subjects_json', sa.Text()),
            sa.Column('bands_json', sa.Text()),
            sa.Column('max_score', sa.Float()),
            sa.Column('benchmark_credits', sa.Integer()),
            sa.Column('cutoff', sa.Float()),
            sa.Column('updated_at', sa.DateTime()),
            sa.UniqueConstraint('level', 'body', name='uq_school_exam_config'),
        )
    if not _has_table('school_exam_results'):
        op.create_table(
            'school_exam_results',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id'), nullable=False, index=True),
            sa.Column('level', sa.String(length=10), nullable=False, index=True),
            sa.Column('body', sa.String(length=10), nullable=False),
            sa.Column('exam_year', sa.Integer(), nullable=False, index=True),
            sa.Column('subject', sa.String(length=80), nullable=False),
            sa.Column('score', sa.Float()),
            sa.Column('grade', sa.String(length=4), nullable=False),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('updated_at', sa.DateTime()),
            sa.UniqueConstraint('student_id', 'level', 'body', 'exam_year', 'subject',
                                name='uq_school_exam_result'),
        )
    if not _has_table('school_exam_candidates'):
        op.create_table(
            'school_exam_candidates',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id'), nullable=False, index=True),
            sa.Column('level', sa.String(length=10), nullable=False, index=True),
            sa.Column('body', sa.String(length=10), nullable=False),
            sa.Column('exam_year', sa.Integer(), nullable=False, index=True),
            sa.Column('exam_number', sa.String(length=40)),
            sa.Column('centre', sa.String(length=120)),
            sa.Column('total_score', sa.Float()),
            sa.Column('placement', sa.String(length=150)),
            sa.Column('admitted', sa.Boolean()),
            sa.Column('remarks', sa.String(length=255)),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('updated_at', sa.DateTime()),
            sa.UniqueConstraint('student_id', 'level', 'body', 'exam_year',
                                name='uq_school_exam_candidate'),
        )


def downgrade():
    for t in ('school_exam_candidates', 'school_exam_results', 'school_exam_configs'):
        if _has_table(t):
            op.drop_table(t)
