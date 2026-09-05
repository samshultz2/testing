"""fixed assets: individually-tracked units (spec §4A)

Adds fixed_assets.is_individually_tracked and a new asset_units table — one
row per physical unit (tag, serial, QR token, location, custodian,
condition) for an asset "type" that opts into unit-level tracking instead
of the batch/quantity model. asset_logs.unit_id lets a unit share the same
event ledger a batch already uses, so unit history (transfers, assignment,
disposal) works the same way batch history does.

Revision ID: c54c4e55fe42
Revises: 0a2e93e85437
Create Date: 2026-09-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c54c4e55fe42'
down_revision = '0a2e93e85437'
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(table):
    try:
        return table in set(_insp().get_table_names())
    except Exception:
        return False


def _has_column(table, column):
    if not _has_table(table):
        return False
    try:
        return column in {c['name'] for c in _insp().get_columns(table)}
    except Exception:
        return False


def upgrade():
    if not _has_column('fixed_assets', 'is_individually_tracked'):
        op.add_column('fixed_assets', sa.Column(
            'is_individually_tracked', sa.Boolean(), nullable=False,
            server_default=sa.false()))

    if not _has_table('asset_units'):
        op.create_table(
            'asset_units',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('asset_id', sa.Integer(), sa.ForeignKey('fixed_assets.id'),
                      nullable=False, index=True),
            sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id')),
            sa.Column('unit_tag', sa.String(length=40)),
            sa.Column('serial_number', sa.String(length=80)),
            sa.Column('qr_token', sa.String(length=40)),
            sa.Column('status', sa.String(length=20)),
            sa.Column('condition', sa.String(length=20)),
            sa.Column('location', sa.String(length=150)),
            sa.Column('custodian', sa.String(length=150)),
            sa.Column('is_disposed', sa.Boolean()),
            sa.Column('disposed_on', sa.Date()),
            sa.Column('disposal_amount', sa.Float()),
            sa.Column('created_by', sa.String(length=100)),
            sa.Column('created_at', sa.DateTime()),
            sa.UniqueConstraint('unit_tag', name='uq_asset_units_unit_tag'),
            sa.UniqueConstraint('qr_token', name='uq_asset_units_qr_token'),
        )
        op.create_index('ix_asset_units_asset_id', 'asset_units', ['asset_id'])

    if not _has_column('asset_logs', 'unit_id'):
        op.add_column('asset_logs', sa.Column('unit_id', sa.Integer(), nullable=True))
        # SQLite dev DBs (created via db.create_all, not this migration) don't
        # need this FK added separately; guard so re-running against such a
        # DB — where the column already exists but the constraint doesn't —
        # never errors on Postgres either, where it's the normal path.
        try:
            op.create_foreign_key('fk_asset_logs_unit_id', 'asset_logs', 'asset_units',
                                  ['unit_id'], ['id'])
        except Exception:
            pass
        op.create_index('ix_asset_logs_unit_id', 'asset_logs', ['unit_id'])


def downgrade():
    if _has_column('asset_logs', 'unit_id'):
        with op.batch_alter_table('asset_logs', schema=None) as batch_op:
            try:
                batch_op.drop_constraint('fk_asset_logs_unit_id', type_='foreignkey')
            except Exception:
                pass
            batch_op.drop_index('ix_asset_logs_unit_id')
            batch_op.drop_column('unit_id')
    if _has_table('asset_units'):
        op.drop_table('asset_units')
    if _has_column('fixed_assets', 'is_individually_tracked'):
        op.drop_column('fixed_assets', 'is_individually_tracked')
