"""fixed assets: temporary loans/checkout

Adds asset_loans table — a parallel, temporary "what's out right now, to
whom, is it overdue" ledger for batch assets (some quantity) and individual
units, distinct from a permanent transfer/assignment. E.g. laptops handed to
teachers to enter exam results, then returned.

Revision ID: dadecafed006
Revises: bdc031379f64
Create Date: 2026-09-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dadecafed006'
down_revision = 'bdc031379f64'
branch_labels = None
depends_on = None


def _has_table(table):
    try:
        return table in set(sa.inspect(op.get_bind()).get_table_names())
    except Exception:
        return False


def upgrade():
    if not _has_table('asset_loans'):
        op.create_table(
            'asset_loans',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('asset_id', sa.Integer(), sa.ForeignKey('fixed_assets.id'),
                      nullable=False, index=True),
            sa.Column('unit_id', sa.Integer(), sa.ForeignKey('asset_units.id'), index=True),
            sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id')),
            sa.Column('borrower', sa.String(length=150), nullable=False),
            sa.Column('purpose', sa.String(length=300)),
            sa.Column('quantity', sa.Integer()),
            sa.Column('checked_out_at', sa.DateTime()),
            sa.Column('due_back', sa.Date()),
            sa.Column('returned_at', sa.DateTime()),
            sa.Column('return_note', sa.Text()),
            sa.Column('note', sa.Text()),
            sa.Column('created_by', sa.String(length=100)),
            sa.Column('created_at', sa.DateTime()),
        )


def downgrade():
    if _has_table('asset_loans'):
        op.drop_table('asset_loans')
