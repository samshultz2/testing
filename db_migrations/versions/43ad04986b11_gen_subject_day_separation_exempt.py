"""add gen_subject_configs.day_separation_exempt

Lets a subject opt OUT of the school-wide day-separation default (Rules ->
Scheduling Constraints): everything else stays subject to it unless exempted
here — e.g. a subject taught every school day, for which "don't land on both
Monday and Friday" is structurally impossible to honour.

Revision ID: 43ad04986b11
Revises: 9d311b647d15
Create Date: 2026-09-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '43ad04986b11'
down_revision = '9d311b647d15'
branch_labels = None
depends_on = None


def _has_column(table, column):
    bind = op.get_bind()
    return column in {c['name'] for c in sa.inspect(bind).get_columns(table)}


def upgrade():
    if not _has_column('gen_subject_configs', 'day_separation_exempt'):
        op.add_column('gen_subject_configs',
                      sa.Column('day_separation_exempt', sa.Boolean(), nullable=True))


def downgrade():
    if _has_column('gen_subject_configs', 'day_separation_exempt'):
        op.drop_column('gen_subject_configs', 'day_separation_exempt')
