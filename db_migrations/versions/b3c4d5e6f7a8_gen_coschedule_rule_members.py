"""timetable generator: co-schedule rules become groups of 2+ members

GenCoScheduleRule used to be strictly pairwise (fixed source_* / target_*
columns), so a school with 3 or 4 combined-class arms that all need to land
in the same slot together had to fake it with overlapping pairs, which the
display-annotation logic couldn't reliably follow past the first match.

This adds gen_co_schedule_rule_members (one row per class+arm+subject slot
in a group, unique per rule+class+arm), backfills each existing rule's
source/target pair as two member rows, then drops the now-redundant
source_*/target_* columns from gen_co_schedule_rules.

Revision ID: b3c4d5e6f7a8
Revises: aed31d3c70aa
Create Date: 2026-09-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b3c4d5e6f7a8'
down_revision = 'aed31d3c70aa'
branch_labels = None
depends_on = None


def _has_table(name):
    try:
        return name in set(sa.inspect(op.get_bind()).get_table_names())
    except Exception:
        return False


def _has_column(table, column):
    try:
        return column in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return False


def upgrade():
    bind = op.get_bind()

    if not _has_table('gen_co_schedule_rule_members'):
        op.create_table(
            'gen_co_schedule_rule_members',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('rule_id', sa.Integer(), sa.ForeignKey('gen_co_schedule_rules.id'),
                      nullable=False, index=True),
            sa.Column('subject_id', sa.Integer(), sa.ForeignKey('gen_subjects.id'), nullable=False),
            sa.Column('class_name', sa.String(length=20), nullable=False),
            sa.Column('arm_name', sa.String(length=50), nullable=False),
            sa.UniqueConstraint('rule_id', 'class_name', 'arm_name',
                                name='uq_gen_coschedule_member_rule_arm'),
        )

    # Backfill: while the old source_*/target_* columns still exist on
    # gen_co_schedule_rules, turn each rule into a 2-member group.
    if _has_column('gen_co_schedule_rules', 'source_subject_id'):
        rows = bind.execute(sa.text(
            'SELECT id, source_subject_id, source_class_name, source_arm_name, '
            'target_subject_id, target_class_name, target_arm_name '
            'FROM gen_co_schedule_rules'
        )).fetchall()
        for r in rows:
            (rule_id, src_subj, src_class, src_arm,
             tgt_subj, tgt_class, tgt_arm) = r
            existing = bind.execute(sa.text(
                'SELECT COUNT(*) FROM gen_co_schedule_rule_members WHERE rule_id = :rid'
            ), {'rid': rule_id}).scalar()
            if existing:
                continue  # already backfilled (re-run safety)
            bind.execute(sa.text(
                'INSERT INTO gen_co_schedule_rule_members '
                '(rule_id, subject_id, class_name, arm_name) VALUES '
                '(:rid, :sid, :cname, :aname)'
            ), {'rid': rule_id, 'sid': src_subj, 'cname': src_class, 'aname': src_arm})
            bind.execute(sa.text(
                'INSERT INTO gen_co_schedule_rule_members '
                '(rule_id, subject_id, class_name, arm_name) VALUES '
                '(:rid, :sid, :cname, :aname)'
            ), {'rid': rule_id, 'sid': tgt_subj, 'cname': tgt_class, 'aname': tgt_arm})

        with op.batch_alter_table('gen_co_schedule_rules', schema=None) as b:
            b.drop_column('source_subject_id')
            b.drop_column('source_class_name')
            b.drop_column('source_arm_name')
            b.drop_column('target_subject_id')
            b.drop_column('target_class_name')
            b.drop_column('target_arm_name')


def downgrade():
    bind = op.get_bind()

    if not _has_column('gen_co_schedule_rules', 'source_subject_id'):
        # Plain columns (no inline FK) -- SQLite's batch/recreate-table mode
        # requires every constraint to be named, and these are only being
        # restored best-effort for a downgrade, not re-enforced.
        with op.batch_alter_table('gen_co_schedule_rules', schema=None) as b:
            b.add_column(sa.Column('source_subject_id', sa.Integer()))
            b.add_column(sa.Column('source_class_name', sa.String(length=20)))
            b.add_column(sa.Column('source_arm_name', sa.String(length=50)))
            b.add_column(sa.Column('target_subject_id', sa.Integer()))
            b.add_column(sa.Column('target_class_name', sa.String(length=20)))
            b.add_column(sa.Column('target_arm_name', sa.String(length=50)))

        if _has_table('gen_co_schedule_rule_members'):
            rule_ids = [row[0] for row in bind.execute(sa.text('SELECT id FROM gen_co_schedule_rules'))]
            for rid in rule_ids:
                members = bind.execute(sa.text(
                    'SELECT subject_id, class_name, arm_name FROM gen_co_schedule_rule_members '
                    'WHERE rule_id = :rid ORDER BY id LIMIT 2'
                ), {'rid': rid}).fetchall()
                if len(members) < 2:
                    continue  # a 1-member or 3+-member group doesn't fit back into a pair; drop it
                (src_subj, src_class, src_arm), (tgt_subj, tgt_class, tgt_arm) = members[0], members[1]
                bind.execute(sa.text(
                    'UPDATE gen_co_schedule_rules SET '
                    'source_subject_id = :ssid, source_class_name = :scname, source_arm_name = :saname, '
                    'target_subject_id = :tsid, target_class_name = :tcname, target_arm_name = :taname '
                    'WHERE id = :rid'
                ), {'ssid': src_subj, 'scname': src_class, 'saname': src_arm,
                    'tsid': tgt_subj, 'tcname': tgt_class, 'taname': tgt_arm, 'rid': rid})

    if _has_table('gen_co_schedule_rule_members'):
        op.drop_table('gen_co_schedule_rule_members')
