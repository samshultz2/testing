"""fee_payment_items — which fee items a payment was for

Revision ID: 8f2b4d6a1c3e
Revises: 7e1a3c5b9d2f
Create Date: 2026-11-17 08:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '8f2b4d6a1c3e'
down_revision = '7e1a3c5b9d2f'
branch_labels = None
depends_on = None


def upgrade():
    if not sa.inspect(op.get_bind()).has_table('fee_payment_items'):
        op.create_table(
            'fee_payment_items',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('payment_id', sa.Integer(), sa.ForeignKey('fee_payments.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('fee_item_id', sa.Integer(), sa.ForeignKey('fee_items.id'), nullable=False),
            sa.Column('amount', sa.Float(), nullable=False),
        )
        op.create_index('ix_fee_payment_items_payment_id', 'fee_payment_items', ['payment_id'])
        op.create_index('ix_fee_payment_items_fee_item_id', 'fee_payment_items', ['fee_item_id'])


def downgrade():
    if sa.inspect(op.get_bind()).has_table('fee_payment_items'):
        op.drop_index('ix_fee_payment_items_fee_item_id', table_name='fee_payment_items')
        op.drop_index('ix_fee_payment_items_payment_id', table_name='fee_payment_items')
        op.drop_table('fee_payment_items')
