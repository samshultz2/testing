"""mock waec result is_absent

Revision ID: fe0d92ec9a80
Revises: ac9d0db57202
Create Date: 2026-10-11 19:19:44.382881

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fe0d92ec9a80'
down_revision = 'ac9d0db57202'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        with op.batch_alter_table('mock_waec_results', schema=None) as batch_op:
            batch_op.add_column(sa.Column('is_absent', sa.Boolean(), nullable=True))
    else:
        op.add_column('mock_waec_results', sa.Column('is_absent', sa.Boolean(), nullable=True))


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        with op.batch_alter_table('mock_waec_results', schema=None) as batch_op:
            batch_op.drop_column('is_absent')
    else:
        op.drop_column('mock_waec_results', 'is_absent')
