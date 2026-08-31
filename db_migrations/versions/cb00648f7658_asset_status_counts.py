"""fixed assets: per-status quantity split

Adds asset_status_counts — one row per (asset, status) with a quantity, so a
single FixedAsset row can be broken down (e.g. 30 laptops: 25 In Use, 3 Under
Repair, 2 Lost) instead of carrying one status for the whole quantity. Every
chart/table/filter on the assets screen reads from here when it exists,
falling back to the asset's plain `status` column for assets that were never
split. Fully guarded/idempotent, matching the self-heal in
utils/finance_ledger.py.

Revision ID: cb00648f7658
Revises: 2369d2ba24fe
Create Date: 2026-08-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cb00648f7658'
down_revision = '2369d2ba24fe'
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(table):
    return table in set(_insp().get_table_names())


def upgrade():
    if not _has_table('asset_status_counts'):
        op.create_table(
            'asset_status_counts',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('asset_id', sa.Integer(), sa.ForeignKey('fixed_assets.id'),
                      nullable=False, index=True),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.Column('quantity', sa.Integer(), nullable=False, server_default='0'),
            sa.UniqueConstraint('asset_id', 'status', name='uq_asset_status_counts'),
        )


def downgrade():
    if _has_table('asset_status_counts'):
        op.drop_table('asset_status_counts')
