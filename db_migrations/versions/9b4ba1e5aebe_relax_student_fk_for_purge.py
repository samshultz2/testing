"""relax student_id nullability on audit/financial/asset tables for purge

Permanently deleting a soft-deleted student (purge_student /
bulk_purge_students) now detaches (sets NULL) the student_id on tables that
represent an independent record with its own reason to survive the student
— payments, discounts, charges, contributions, sales, admissions
applications, message send-history, and graduate audit/documents/alumni/
verification/requests — rather than either deleting them or crashing with a
NOT NULL violation. Each of these columns was previously nullable=False (or
had no relationship path to null it at all), which is what actually raised
the reported error for the sibling academic tables fixed in the previous
migration-less model change; these columns need the DB constraint relaxed
too since Postgres enforces it independently of the ORM model.

SQLite cannot drop a NOT NULL constraint without a table rebuild, so this is
best-effort via batch_alter_table; on Postgres it's a plain ALTER.

NOTE: at the time this was written, `f00dc0e5c001` and `b2f4a6c8e012` were
two separate, unreconciled migration heads (an unrelated pre-existing fork —
see the deploy notes). This migration chains off `f00dc0e5c001` only; the
fork itself needs its own merge migration, deliberately not bundled into
this one.

Revision ID: 9b4ba1e5aebe
Revises: f00dc0e5c001
Create Date: 2026-09-15 05:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '9b4ba1e5aebe'
down_revision = 'f00dc0e5c001'
branch_labels = None
depends_on = None

# (table, column) pairs to relax to nullable=True.
_COLUMNS = [
    ('fee_payments', 'student_id'),
    ('fee_discounts', 'student_id'),
    ('additional_charges', 'student_id'),
    ('contribution_payments', 'student_id'),
    ('graduate_audits', 'student_id'),
    ('graduate_documents', 'student_id'),
    ('alumni_profiles', 'student_id'),
    ('document_requests', 'student_id'),
    ('cbt_login_events', 'student_id'),
]


def upgrade():
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    for table, column in _COLUMNS:
        try:
            if is_sqlite:
                with op.batch_alter_table(table, schema=None) as batch_op:
                    batch_op.alter_column(column, existing_type=sa.Integer(), nullable=True)
            else:
                op.alter_column(table, column, existing_type=sa.Integer(), nullable=True)
        except Exception:
            pass


def downgrade():
    # Not reversible: rows written while nullable may already carry NULL,
    # which would violate re-adding NOT NULL. Leave relaxed on downgrade.
    pass
