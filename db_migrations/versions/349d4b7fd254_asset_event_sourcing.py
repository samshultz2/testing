"""fixed assets: event-sourced state (breakdown_snapshot on asset_logs)

Adds asset_logs.breakdown_snapshot (JSON text) — the full per-status
breakdown resulting from each event, e.g. {"In Use": 25, "Under Repair": 3}.
This is what makes FixedAsset.quantity/.status and AssetStatusCount genuinely
DERIVED from the event history instead of independently-maintained fields a
log happens to shadow: they're a cache rebuilt from the latest event's
snapshot (see routes/sales.py recompute_asset_state), never written on their
own. A one-time 'opening_balance' event backfills each existing asset's
current state as its starting point under the new model — preserving
existing data, inventing nothing.

Revision ID: 349d4b7fd254
Revises: a54e69ba715a
Create Date: 2026-09-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '349d4b7fd254'
down_revision = 'a54e69ba715a'
branch_labels = None
depends_on = None


def _has_column(table, column):
    try:
        return column in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return False


def upgrade():
    if not _has_column('asset_logs', 'breakdown_snapshot'):
        op.add_column('asset_logs', sa.Column('breakdown_snapshot', sa.Text(), nullable=True))


def downgrade():
    if _has_column('asset_logs', 'breakdown_snapshot'):
        op.drop_column('asset_logs', 'breakdown_snapshot')
