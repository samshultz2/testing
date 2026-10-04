"""Study/project groups (Tools): group a class's students for group work,
weighted by their performance the term before -- the strongest performers
become group leaders, so each group gets roughly the same mix of ability. A
``GroupSet`` is one generated-and-saved run; its groups and members can be
edited afterward (move a student, change a leader) without regenerating.

Deliberately its own tables, not a reuse of ClassArmAssignment/
StudentEnrollment: "merge two arms for this grouping" must never touch where
a student is actually enrolled -- it only widens the candidate pool for this
one tool."""
from models.models import db, local_now


class GroupSet(db.Model):
    """One generated grouping run for a class (optionally several merged arms)
    in one term."""
    __tablename__ = 'group_sets'

    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'), nullable=False)
    # Comma-separated ClassArm ids whose rosters were merged into the candidate
    # pool for this run -- grouping-only, never written back to enrollment.
    arm_ids = db.Column(db.String(200), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'), nullable=False)
    # The term whose TermSummary.average_score ranked students for this run.
    # NULL when no prior performance data existed at all (e.g. a school's very
    # first term) -- every student was then placed randomly.
    basis_term_id = db.Column(db.Integer, db.ForeignKey('terms.id'))
    group_size = db.Column(db.Integer, nullable=False)   # the target per-group size requested
    num_groups = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(150))
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)

    school_class = db.relationship('SchoolClass')
    term = db.relationship('Term', foreign_keys=[term_id])
    basis_term = db.relationship('Term', foreign_keys=[basis_term_id])
    groups = db.relationship('StudentGroup', backref='group_set',
                             cascade='all, delete-orphan',
                             order_by='StudentGroup.position')

    @property
    def arm_id_list(self):
        return [int(x) for x in (self.arm_ids or '').split(',') if x.strip().isdigit()]


class StudentGroup(db.Model):
    """One group within a GroupSet."""
    __tablename__ = 'student_groups'

    id = db.Column(db.Integer, primary_key=True)
    group_set_id = db.Column(db.Integer, db.ForeignKey('group_sets.id'), nullable=False)
    position = db.Column(db.Integer, nullable=False)   # 1, 2, 3... display order
    label = db.Column(db.String(80))                    # editable; defaults to "Group {position}"
    leader_student_id = db.Column(db.Integer, db.ForeignKey('students.id'))

    leader = db.relationship('Student', foreign_keys=[leader_student_id])
    members = db.relationship('GroupMember', backref='group',
                              cascade='all, delete-orphan', order_by='GroupMember.id')

    @property
    def display_label(self):
        return self.label or f'Group {self.position}'


class GroupMember(db.Model):
    """One student's placement in one group of one GroupSet."""
    __tablename__ = 'group_members'

    id = db.Column(db.Integer, primary_key=True)
    # Redundant with group.group_set_id, kept directly here so "this student is
    # already placed somewhere in this set" can be checked/enforced without a
    # join, and so moving a student between groups never needs to touch it.
    group_set_id = db.Column(db.Integer, db.ForeignKey('group_sets.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('student_groups.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    # Snapshot of the previous term's average used to place this student, at
    # generation time -- NULL for a randomly-placed (new/no-data) student.
    # Kept even if the student is later moved, so the group board can still
    # show "why" a student was ranked where they were.
    basis_average = db.Column(db.Float)

    student = db.relationship('Student')

    __table_args__ = (
        db.UniqueConstraint('group_set_id', 'student_id', name='uq_group_member_once_per_set'),
    )
