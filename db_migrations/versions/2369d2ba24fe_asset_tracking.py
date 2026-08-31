"""fixed assets: optional class/arm/teacher/section links + history ledger

Adds optional ownership/placement columns to fixed_assets (class_id, arm_id,
teacher_id, section — every one nullable, an asset may carry any subset of
them) and a new asset_logs table recording each meaningful change to an asset
(registered, quantity changed, status changed, edited, disposed, restored),
tagged with the session/term active at the time. This is what lets the assets
screen compare "last term vs this term" / "last session vs this session" /
"last week vs this week" quantities per asset, per category, and in total.
Fully guarded/idempotent, matching the self-heal in utils/finance_ledger.py.

Revision ID: 2369d2ba24fe
Revises: f0c1d2e3f4a5
Create Date: 2026-08-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2369d2ba24fe'
down_revision = 'f0c1d2e3f4a5'
branch_labels = None
depends_on = None


_FIXED_ASSET_COLUMNS = [
    ('class_id', sa.Integer()),
    ('arm_id', sa.Integer()),
    ('teacher_id', sa.Integer()),
    ('section', sa.String(length=20)),
]


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(table):
    return table in set(_insp().get_table_names())


def _has_column(table, column):
    if not _has_table(table):
        return False
    return column in {c['name'] for c in _insp().get_columns(table)}


def upgrade():
    for name, type_ in _FIXED_ASSET_COLUMNS:
        if not _has_column('fixed_assets', name):
            op.add_column('fixed_assets', sa.Column(name, type_, nullable=True))

    if not _has_table('asset_logs'):
        op.create_table(
            'asset_logs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('asset_id', sa.Integer(), sa.ForeignKey('fixed_assets.id'),
                      nullable=False, index=True),
            sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id')),
            sa.Column('event_type', sa.String(length=20), nullable=False),
            sa.Column('quantity_before', sa.Integer()),
            sa.Column('quantity_after', sa.Integer()),
            sa.Column('status_before', sa.String(length=20)),
            sa.Column('status_after', sa.String(length=20)),
            sa.Column('note', sa.String(length=255)),
            sa.Column('session_id', sa.Integer(), sa.ForeignKey('academic_sessions.id')),
            sa.Column('term_id', sa.Integer(), sa.ForeignKey('terms.id')),
            sa.Column('created_by', sa.String(length=100)),
            sa.Column('created_at', sa.DateTime(), index=True),
        )


def downgrade():
    if _has_table('asset_logs'):
        op.drop_table('asset_logs')
    for name, _type in _FIXED_ASSET_COLUMNS:
        if _has_column('fixed_assets', name):
            op.drop_column('fixed_assets', name)
