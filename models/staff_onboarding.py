"""Staff self-onboarding via shareable invite links.

Flow: an authorised admin generates a reusable invite link that fixes the role /
permission-group new joiners will get. Staff open the link, fill in their details
+ a password (and pick their branch unless the link pins one), and submit. Nothing
is granted yet — the submission lands as a ``StaffSignup`` (pending), OUTSIDE the
users table, so a pending row can never log in or hold permissions. An admin then
approves it, at which point the real ``User`` is created with the invite's role,
permission group and branch.
"""
from datetime import datetime, timedelta
import secrets

from models.models import db, local_now


class StaffInvite(db.Model):
    """A reusable sign-up link. Fixes the role + permission group joiners receive
    on approval; each joiner picks their own branch unless ``branch_id`` pins one."""
    __tablename__ = 'staff_invites'

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    label = db.Column(db.String(120))                 # e.g. "Branch Principals 2026"
    role = db.Column(db.String(20), default='staff')  # User.role granted on approval
    permission_group_id = db.Column(db.Integer, db.ForeignKey('permission_groups.id'))
    # If set, every joiner on this link is pinned to this branch; else they choose.
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    scope = db.Column(db.String(10), default='branch')   # 'central' for cross-branch roles
    max_uses = db.Column(db.Integer)                  # NULL = unlimited
    uses = db.Column(db.Integer, default=0)
    expires_at = db.Column(db.DateTime)               # NULL = never
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.String(80))             # username of the generator
    created_at = db.Column(db.DateTime, default=local_now)
    # Optional preset job title (e.g. "SSS3 Form Teacher"), pre-filled/locked on
    # the join form; and the set of optional fields the join form exposes (JSON
    # list). NULL fields = show them all (legacy behaviour).
    position = db.Column(db.String(80))
    fields = db.Column(db.Text)

    permission_group = db.relationship('PermissionGroup', foreign_keys=[permission_group_id])
    branch = db.relationship('Branch', foreign_keys=[branch_id])

    # Optional join-form fields an invite may switch on/off (the core name /
    # username / password / branch are always present).
    OPTIONAL_FIELDS = ('email', 'phone', 'position', 'gender', 'staff_type',
                       'department', 'qualification')

    @property
    def field_set(self):
        """The optional fields this invite's join form should show. A legacy invite
        (``fields`` NULL) exposes them all."""
        import json
        if not self.fields:
            return set(self.OPTIONAL_FIELDS)
        try:
            return {v for v in json.loads(self.fields) if v in self.OPTIONAL_FIELDS}
        except Exception:
            return set(self.OPTIONAL_FIELDS)

    def shows(self, field):
        return field in self.field_set

    @staticmethod
    def new_token():
        return secrets.token_urlsafe(24)

    @property
    def expired(self):
        return bool(self.expires_at and local_now() >= self.expires_at)

    @property
    def used_up(self):
        return bool(self.max_uses and (self.uses or 0) >= self.max_uses)

    @property
    def usable(self):
        return bool(self.is_active) and not self.expired and not self.used_up


class StaffSignup(db.Model):
    """A submitted-but-unapproved staff sign-up. Held out of the users table until
    an admin approves, so pending rows never grant access."""
    __tablename__ = 'staff_signups'

    id = db.Column(db.Integer, primary_key=True)
    invite_id = db.Column(db.Integer, db.ForeignKey('staff_invites.id'))
    full_name = db.Column(db.String(120))
    username = db.Column(db.String(50))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(30))
    password_hash = db.Column(db.String(256))         # already hashed at submit time
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    position = db.Column(db.String(80))               # free-text title the joiner enters
    # Extra bio the joiner supplies so approval can create their HR record too.
    gender = db.Column(db.String(10))
    staff_type = db.Column(db.String(20))             # Teaching / Non-teaching
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    qualification = db.Column(db.String(200))
    status = db.Column(db.String(12), default='pending')   # pending / approved / rejected
    created_at = db.Column(db.DateTime, default=local_now)
    reviewed_by = db.Column(db.String(80))
    reviewed_at = db.Column(db.DateTime)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))   # the created user on approval

    invite = db.relationship('StaffInvite', foreign_keys=[invite_id])
    branch = db.relationship('Branch', foreign_keys=[branch_id])
