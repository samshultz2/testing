"""add after_period to timetable_slots, backfill from current position

TimetableSlot had no explicit field recording which teaching period a break
belongs after — ordering was inferred purely from whatever start_time/end_time
happened to be stored, which drifted silently whenever a slot was hand-edited
or periods were appended (e.g. via the generator's auto-extend) without the
break being moved too. repair_slot_schedule() only fixed a break that
literally overlapped a period's clock time; a break sitting in the wrong
*sequence* without overlapping anything was never touched.

This adds ``after_period`` (nullable int, meaningful only for is_break rows):
"this break comes immediately after the Nth teaching period". Existing break
rows are backfilled with the number of active teaching periods that
currently sort before them, so already-correct schedules keep behaving
exactly as before — the field simply makes today's inferred position
explicit and editable, and gives the self-heal something definitive to
enforce going forward.

Revision ID: 7a99ffe8e3f4
Revises: 9b0dbe1ee80e
Create Date: 2026-09-16 04:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '7a99ffe8e3f4'
down_revision = '9b0dbe1ee80e'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    if is_sqlite:
        with op.batch_alter_table('timetable_slots', schema=None) as batch_op:
            batch_op.add_column(sa.Column('after_period', sa.Integer(), nullable=True))
    else:
        op.add_column('timetable_slots', sa.Column('after_period', sa.Integer(), nullable=True))

    # Backfill: for each active break, count active teaching periods whose
    # start_time sorts before it. Best-effort — any failure here just leaves
    # after_period NULL (falls back to the old overlap-only repair), it never
    # blocks the column from being added.
    try:
        meta = sa.MetaData()
        slots = sa.Table('timetable_slots', meta, autoload_with=bind)
        rows = bind.execute(sa.select(slots.c.id, slots.c.is_break, slots.c.start_time)
                            .where(slots.c.is_active == True)).fetchall()  # noqa: E712
        teaching_times = sorted(r.start_time for r in rows if not r.is_break and r.start_time is not None)
        for r in rows:
            if not r.is_break or r.start_time is None:
                continue
            n = sum(1 for t in teaching_times if t is not None and t < r.start_time)
            bind.execute(slots.update().where(slots.c.id == r.id).values(after_period=n))
    except Exception:
        pass


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        with op.batch_alter_table('timetable_slots', schema=None) as batch_op:
            batch_op.drop_column('after_period')
    else:
        op.drop_column('timetable_slots', 'after_period')
