"""staff invites: preset position + per-invite field selection

Adds staff_invites.position and staff_invites.fields. Guarded/idempotent — a
no-op on databases that already received these via the runtime self-heal or
create_all.

Revision ID: f0c1d2e3f4a5
Revises: f9b0c1d2e3f4
Create Date: 2026-08-13 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f0c1d2e3f4a5'
down_revision = 'f9b0c1d2e3f4'
branch_labels = None
depends_on = None

_COLUMNS = [('position', sa.String(length=80)), ('fields', sa.Text())]


def _has_column(table, column):
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in set(insp.get_table_names()):
        return True   # table absent → nothing to add here
    return column in {c['name'] for c in insp.get_columns(table)}


def upgrade():
    for name, type_ in _COLUMNS:
        if not _has_column('staff_invites', name):
            op.add_column('staff_invites', sa.Column(name, type_, nullable=True))


def downgrade():
    for name, _type in _COLUMNS:
        if _has_column('staff_invites', name):
            op.drop_column('staff_invites', name)
