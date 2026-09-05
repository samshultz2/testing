"""fixed assets: maintenance history (spec §12)

Adds asset_maintenance table — one row per maintenance event for a batch
asset or an individual unit, recording problem, diagnosis, action, technician,
cost, parts, warranty coverage, downtime, and next maintenance date. Feeds
both the per-asset maintenance tab and the 'is this asset becoming
uneconomical to maintain?' management question.

Revision ID: 76b1f7eea06c
Revises: c54c4e55fe42
Create Date: 2026-09-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '76b1f7eea06c'
down_revision = 'c54c4e55fe42'
branch_labels = None
depends_on = None


def _has_table(table):
    try:
        return table in set(sa.inspect(op.get_bind()).get_table_names())
    except Exception:
        return False


def upgrade():
    if not _has_table('asset_maintenance'):
        op.create_table(
            'asset_maintenance',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('asset_id', sa.Integer(), sa.ForeignKey('fixed_assets.id'),
                      nullable=False, index=True),
            sa.Column('unit_id', sa.Integer(), sa.ForeignKey('asset_units.id'), index=True),
            sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id')),
            sa.Column('status', sa.String(length=20)),
            sa.Column('problem', sa.String(length=500)),
            sa.Column('diagnosis', sa.String(length=500)),
            sa.Column('action_taken', sa.String(length=500)),
            sa.Column('technician', sa.String(length=150)),
            sa.Column('started_on', sa.Date()),
            sa.Column('completed_on', sa.Date()),
            sa.Column('next_maintenance_on', sa.Date()),
            sa.Column('cost', sa.Float()),
            sa.Column('parts_used', sa.Text()),
            sa.Column('warranty_covered', sa.Boolean()),
            sa.Column('reference', sa.String(length=80)),
            sa.Column('notes', sa.Text()),
            sa.Column('created_by', sa.String(length=100)),
            sa.Column('created_at', sa.DateTime()),
        )


def downgrade():
    if _has_table('asset_maintenance'):
        op.drop_table('asset_maintenance')
