"""fixed assets: physical verification audit (spec §10)

Adds asset_audits and asset_audit_items tables. An AssetAudit is a named
verification exercise ('Q1 2026 ICT Audit'); the system generates the
expected item list; staff mark each Verified/Missing/Damaged/Wrong Location;
the final report shows what was found vs. expected. Missing items go to
'Under Investigation' — not 'permanently lost' (per spec §10).

Revision ID: bdc031379f64
Revises: 76b1f7eea06c
Create Date: 2026-09-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bdc031379f64'
down_revision = '76b1f7eea06c'
branch_labels = None
depends_on = None


def _has_table(table):
    try:
        return table in set(sa.inspect(op.get_bind()).get_table_names())
    except Exception:
        return False


def upgrade():
    if not _has_table('asset_audits'):
        op.create_table(
            'asset_audits',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id')),
            sa.Column('name', sa.String(length=200), nullable=False),
            sa.Column('description', sa.Text()),
            sa.Column('status', sa.String(length=20)),
            sa.Column('category_filter', sa.String(length=100)),
            sa.Column('started_on', sa.Date()),
            sa.Column('completed_on', sa.Date()),
            sa.Column('created_by', sa.String(length=100)),
            sa.Column('created_at', sa.DateTime()),
        )
    if not _has_table('asset_audit_items'):
        op.create_table(
            'asset_audit_items',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('audit_id', sa.Integer(), sa.ForeignKey('asset_audits.id'),
                      nullable=False, index=True),
            sa.Column('asset_id', sa.Integer(), sa.ForeignKey('fixed_assets.id'),
                      nullable=False, index=True),
            sa.Column('unit_id', sa.Integer(), sa.ForeignKey('asset_units.id'), index=True),
            sa.Column('state', sa.String(length=30)),
            sa.Column('expected_location', sa.String(length=150)),
            sa.Column('found_location', sa.String(length=150)),
            sa.Column('note', sa.String(length=500)),
            sa.Column('verified_by', sa.String(length=100)),
            sa.Column('verified_at', sa.DateTime()),
            sa.Column('quantity_expected', sa.Integer()),
            sa.Column('quantity_found', sa.Integer()),
        )


def downgrade():
    if _has_table('asset_audit_items'):
        op.drop_table('asset_audit_items')
    if _has_table('asset_audits'):
        op.drop_table('asset_audits')
