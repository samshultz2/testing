"""subjects: JSS/SSS level classification

Adds for_junior/for_senior to subjects, so a subject can be tagged as
applying to Junior Secondary, Senior Secondary, or both — the assign-subjects
picker and the subjects list use this to filter/group by level. Both default
TRUE so every existing subject keeps showing everywhere it already did.
Fully guarded/idempotent, matching the self-heal in utils/subjects_schema.py.

Revision ID: a54e69ba715a
Revises: cb00648f7658
Create Date: 2026-09-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a54e69ba715a'
down_revision = 'cb00648f7658'
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_column(table, column):
    try:
        return column in {c['name'] for c in _insp().get_columns(table)}
    except Exception:
        return False


def upgrade():
    if not _has_column('subjects', 'for_junior'):
        op.add_column('subjects', sa.Column('for_junior', sa.Boolean(), nullable=True,
                                            server_default=sa.true()))
    if not _has_column('subjects', 'for_senior'):
        op.add_column('subjects', sa.Column('for_senior', sa.Boolean(), nullable=True,
                                            server_default=sa.true()))
    conn = op.get_bind()
    conn.execute(sa.text('UPDATE subjects SET for_junior = TRUE WHERE for_junior IS NULL'))
    conn.execute(sa.text('UPDATE subjects SET for_senior = TRUE WHERE for_senior IS NULL'))


def downgrade():
    if _has_column('subjects', 'for_junior'):
        op.drop_column('subjects', 'for_junior')
    if _has_column('subjects', 'for_senior'):
        op.drop_column('subjects', 'for_senior')
