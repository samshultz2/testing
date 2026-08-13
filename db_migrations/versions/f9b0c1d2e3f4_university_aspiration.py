"""university aspiration: student target/admission columns + reference tables

Adds the university-aspiration schema so every provisioning path agrees
(create_all, alembic upgrade, migrate_all_tenants). Fully guarded/idempotent —
it only adds a column or creates a table when missing, so it is safe on databases
that already received these via the runtime self-heal.

Revision ID: f9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-08-13 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f9b0c1d2e3f4'
down_revision = 'f8a9b0c1d2e3'
branch_labels = None
depends_on = None


# students columns added by this feature: (name, type). Kept plain (no DB-level
# FK constraint) to match what the runtime self-heal already added on live DBs.
_STUDENT_COLUMNS = [
    ('target_university_id', sa.Integer()),
    ('target_course_id', sa.Integer()),
    ('target_department', sa.String(length=120)),
    ('target2_university_id', sa.Integer()),
    ('target2_course_id', sa.Integer()),
    ('career_goal', sa.String(length=120)),
    ('admission_status', sa.String(length=20)),
    ('admitted_university_id', sa.Integer()),
    ('admitted_course_id', sa.Integer()),
]


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(table):
    return table in set(_insp().get_table_names())


def _has_column(table, column):
    if not _has_table(table):
        return False
    return column in {c['name'] for c in _insp().get_columns(table)}


def upgrade():
    # Reference tables (create only if absent).
    if not _has_table('universities'):
        op.create_table(
            'universities',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('name', sa.String(length=160), nullable=False, unique=True),
            sa.Column('abbreviation', sa.String(length=20)),
            sa.Column('state', sa.String(length=60)),
            sa.Column('ownership', sa.String(length=20)),
            sa.Column('cutoff_bump', sa.Integer()),
            sa.Column('is_active', sa.Boolean()),
            sa.Column('created_at', sa.DateTime()),
        )
    if not _has_table('courses'):
        op.create_table(
            'courses',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('name', sa.String(length=160), nullable=False, unique=True),
            sa.Column('department', sa.String(length=120)),
            sa.Column('base_cutoff', sa.Integer()),
            sa.Column('jamb_subjects', sa.Text()),
            sa.Column('waec_subjects', sa.Text()),
            sa.Column('is_active', sa.Boolean()),
            sa.Column('created_at', sa.DateTime()),
        )
    if not _has_table('university_courses'):
        op.create_table(
            'university_courses',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('university_id', sa.Integer(), sa.ForeignKey('universities.id'),
                      nullable=False, index=True),
            sa.Column('course_id', sa.Integer(), sa.ForeignKey('courses.id'),
                      nullable=False, index=True),
            sa.Column('jamb_cutoff', sa.Integer(), nullable=False),
            sa.Column('is_active', sa.Boolean()),
            sa.Column('created_at', sa.DateTime()),
            sa.UniqueConstraint('university_id', 'course_id', name='uq_university_course'),
        )
    if not _has_table('student_scholarships'):
        op.create_table(
            'student_scholarships',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id'),
                      nullable=False, index=True),
            sa.Column('name', sa.String(length=160), nullable=False),
            sa.Column('provider', sa.String(length=160)),
            sa.Column('amount', sa.Float()),
            sa.Column('status', sa.String(length=20)),
            sa.Column('notes', sa.Text()),
            sa.Column('created_at', sa.DateTime()),
        )

    # Student columns (each only if missing).
    for name, type_ in _STUDENT_COLUMNS:
        if not _has_column('students', name):
            op.add_column('students', sa.Column(name, type_, nullable=True))


def downgrade():
    for name, _type in _STUDENT_COLUMNS:
        if _has_column('students', name):
            op.drop_column('students', name)
    for table in ('student_scholarships', 'university_courses', 'courses', 'universities'):
        if _has_table(table):
            op.drop_table(table)
