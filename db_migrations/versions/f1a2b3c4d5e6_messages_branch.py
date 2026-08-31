"""communication: per-branch campaigns (messages.branch_id)

Adds branch_id to messages so SMS/WhatsApp campaigns belong to a branch (for
branch-scoped lists and access control) and backfills existing rows to the
default branch so they aren't left world-readable.

Revision ID: f1a2b3c4d5e6
Revises: e7f3a9b2c1d8
Create Date: 2026-06-15 16:20:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'f1a2b3c4d5e6'
down_revision = 'e7f3a9b2c1d8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('branch_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_messages_branch_id', 'branches', ['branch_id'], ['id'])
    op.execute(
        "UPDATE messages SET branch_id = "
        "(SELECT id FROM branches WHERE is_default = 1 ORDER BY id LIMIT 1) "
        "WHERE branch_id IS NULL"
    )
    op.execute(
        "UPDATE messages SET branch_id = (SELECT MIN(id) FROM branches) "
        "WHERE branch_id IS NULL"
    )


def downgrade():
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_constraint('fk_messages_branch_id', type_='foreignkey')
        batch_op.drop_column('branch_id')
