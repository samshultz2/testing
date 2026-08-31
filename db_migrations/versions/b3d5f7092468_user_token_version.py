"""auth: server-side session revocation (users.token_version)

Adds a token_version to users. The login stamps it into the session and every
request re-checks it, so bumping it (on password change, admin reset, or a
forced sign-out) invalidates all of that user's existing signed-cookie sessions.
Existing rows are backfilled to 1.

Revision ID: b3d5f7092468
Revises: a2c4e6081357
Create Date: 2026-07-05 13:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'b3d5f7092468'
down_revision = 'a2c4e6081357'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('token_version', sa.Integer(),
                                      nullable=False, server_default='1'))
    # Drop the server_default now that existing rows are populated; the model
    # supplies the default for new rows.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('token_version', server_default=None)


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('token_version')
