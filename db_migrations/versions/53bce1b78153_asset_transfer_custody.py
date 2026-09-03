"""fixed assets: transfer/custody tracking on the event ledger

Adds location_before/after, custodian_before/after, and reference to
asset_logs — so a 'transferred' or 'assigned'/'unassigned' event carries a
full before/after record the same way quantity/status events already do.
This is what lets "where was this asset on date X" and "who has had this
asset" be answered by replaying the ledger, instead of the asset's current
location/custodian being a flat field with no history behind it.

Revision ID: 53bce1b78153
Revises: 349d4b7fd254
Create Date: 2026-09-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '53bce1b78153'
down_revision = '349d4b7fd254'
branch_labels = None
depends_on = None


_NEW_COLUMNS = [
    ('location_before', sa.String(length=150)),
    ('location_after', sa.String(length=150)),
    ('custodian_before', sa.String(length=150)),
    ('custodian_after', sa.String(length=150)),
    ('reference', sa.String(length=80)),
]


def _has_column(table, column):
    try:
        return column in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return False


def upgrade():
    for name, type_ in _NEW_COLUMNS:
        if not _has_column('asset_logs', name):
            op.add_column('asset_logs', sa.Column(name, type_, nullable=True))


def downgrade():
    for name, _type in _NEW_COLUMNS:
        if _has_column('asset_logs', name):
            op.drop_column('asset_logs', name)
