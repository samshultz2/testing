"""SQLAlchemy models — users (split from the former models/models.py).
Base names (db, local_now, EncryptedString, …) come from the package __init__;
sibling models are referenced lazily inside methods as in the original."""
from models.models import *  # noqa: F401,F403


class User(db.Model):
    """Enhanced User accounts for the system with role-based access"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    role = db.Column(db.String(20), default='teacher')  # super_admin, admin, teacher, staff, readonly
    # JSON list of module keys this (non-admin) user may access. Empty/None =>
    # fall back to the role's default module set. Admins ignore this (see all).
    allowed_modules = db.Column(db.Text)
    # JSON dict {module_key: 'view'|'edit'|'none'} — per-user permission OVERRIDES
    # layered on top of the assigned permission group ('none' revokes a
    # group-granted permission). With no group, this is just the user's own perms.
    permissions = db.Column(db.Text)
    # Optional permission-group template (the base permissions for this user).
    permission_group_id = db.Column(db.Integer, db.ForeignKey('permission_groups.id'))
    # When True, the user may browse but cannot create/edit/delete anything
    # (enforced globally for unsafe HTTP methods). The 'readonly' role implies this too.
    view_only = db.Column(db.Boolean, default=False)
    # Multi-branch scope: 'central' users see every branch (Director of Studies,
    # Exams & Standards, IT); 'branch' users are limited to their own branch_id.
    scope = db.Column(db.String(10), default='branch')
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    # Optional sub-branch scoping (Stage 4): a section group ('secondary' or
    # 'primary') and/or a subject stream ('arts'/'science') the user oversees.
    section = db.Column(db.String(20))
    stream = db.Column(db.String(20))
    # Delegated user management: a manager can edit users below their rank.
    # manage_scope: 'none' (can't), 'branch' (own branch, lower rank), 'central' (all).
    rank = db.Column(db.Integer, default=0)
    manage_scope = db.Column(db.String(10), default='none')
    # Preferred UI colour theme (see utils/themes.py).
    theme = db.Column(db.String(20))
    # Force a password change on next login (set for new accounts / admin resets).
    must_change_password = db.Column(db.Boolean, default=False)
    # Single-use, time-limited password-reset token (stored hashed). Used by the
    # self-service reset so we never overwrite the live password before the user
    # actually sets a new one. See routes/auth.py.
    reset_token_hash = db.Column(db.String(256))
    reset_token_expires = db.Column(db.DateTime)
    # Opt-in TOTP 2FA. The base32 secret is encrypted at rest (EncryptedString);
    # backup codes are stored as a JSON list of one-way hashes, shown once.
    mfa_enabled = db.Column(db.Boolean, default=False)
    mfa_secret = db.Column(EncryptedString())
    mfa_backup_codes = db.Column(db.Text)
    # Bumped to invalidate every existing signed-cookie session for this user
    # (server-side revocation): the login stamps this into the session and every
    # request re-checks it, so a password change / admin reset / forced sign-out
    # logs out all other devices. See routes/auth.py and enforce_session_version.
    token_version = db.Column(db.Integer, default=1, nullable=False)
    # Dashboard personalization. Historically a JSON *list* of enabled widget
    # keys; now a JSON *object* {enabled, order, favorites}. Both shapes are read
    # transparently (a bare list is treated as {enabled: list}) so old rows keep
    # working without a migration.
    dashboard_prefs = db.Column(db.Text)

    @property
    def _dash_prefs_obj(self):
        import json
        if not self.dashboard_prefs:
            return {}
        try:
            v = json.loads(self.dashboard_prefs)
        except (ValueError, TypeError):
            return {}
        if isinstance(v, list):
            return {'enabled': v}
        return v if isinstance(v, dict) else {}

    def _save_dash_obj(self, obj):
        import json
        # Drop empty keys so a cleared layout serialises back to null.
        obj = {k: v for k, v in obj.items() if v}
        self.dashboard_prefs = json.dumps(obj) if obj else None

    @property
    def dashboard_widgets(self):
        v = self._dash_prefs_obj.get('enabled')
        return v if isinstance(v, list) else None

    def set_dashboard_widgets(self, keys):
        obj = self._dash_prefs_obj
        if keys is None:
            obj.pop('enabled', None)
        else:
            obj['enabled'] = list(keys)
        self._save_dash_obj(obj)

    @property
    def dashboard_order(self):
        v = self._dash_prefs_obj.get('order')
        return v if isinstance(v, list) else None

    @property
    def dashboard_favorites(self):
        v = self._dash_prefs_obj.get('favorites')
        return v if isinstance(v, list) else None

    def set_dashboard_layout(self, *, enabled=None, order=None, favorites=None):
        """Persist any of enabled / order / favorites, leaving the others intact."""
        obj = self._dash_prefs_obj
        if enabled is not None:
            obj['enabled'] = list(enabled)
        if order is not None:
            obj['order'] = list(order)
        if favorites is not None:
            obj['favorites'] = list(favorites)
        self._save_dash_obj(obj)
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Relationships
    teacher_profile = db.relationship('Teacher', backref='user', uselist=False, cascade='all, delete-orphan')
    created_by = db.relationship('User', remote_side=[id], backref='created_users')
    branch = db.relationship('Branch')
    permission_group = db.relationship('PermissionGroup', foreign_keys=[permission_group_id])

    @property
    def is_central(self):
        """A central user sees across all branches (not limited to branch_id).

        Scope — not role — decides this, so an admin assigned to a branch stays
        scoped to that branch. Super admins are always central.
        """
        return self.role == 'super_admin' or self.scope == 'central'

    def set_password(self, password):
        """Hash and set password. Also revokes existing sessions — any password
        change must not leave old signed-cookie sessions valid."""
        self.password_hash = generate_password_hash(password)
        self.revoke_sessions()

    def revoke_sessions(self):
        """Invalidate every currently-issued session for this user by bumping the
        token version the login stamped into each session cookie. The caller may
        re-stamp the *current* session afterwards to keep it alive (self-service
        password change); an admin reset deliberately does not, forcing re-login."""
        self.token_version = (self.token_version or 1) + 1

    def check_password(self, password):
        """Verify password"""
        # Cap length before hashing — scrypt on an unbounded value is a worker DoS.
        from utils.security import MAX_PASSWORD_LEN
        if not password or len(password) > MAX_PASSWORD_LEN:
            return False
        return check_password_hash(self.password_hash, password)

    # --- TOTP 2FA -----------------------------------------------------------
    @property
    def mfa_backup_code_hashes(self):
        import json
        if not self.mfa_backup_codes:
            return []
        try:
            v = json.loads(self.mfa_backup_codes)
            return v if isinstance(v, list) else []
        except (ValueError, TypeError):
            return []

    def set_mfa_backup_codes(self, hashes):
        import json
        self.mfa_backup_codes = json.dumps(list(hashes)) if hashes else None

    def consume_backup_code(self, code):
        """If `code` matches an unused backup code, remove that hash (one-time
        use) and return True. Caller commits."""
        if not code:
            return False
        import json
        norm = ''.join(ch for ch in str(code).upper() if ch.isalnum())  # drop dashes/spaces
        if not norm:
            return False
        remaining = self.mfa_backup_code_hashes
        for h in remaining:
            if check_password_hash(h, norm):
                remaining = [x for x in remaining if x != h]
                self.mfa_backup_codes = json.dumps(remaining) if remaining else None
                return True
        return False

    def disable_mfa(self):
        self.mfa_enabled = False
        self.mfa_secret = None
        self.mfa_backup_codes = None

    def set_reset_token(self, ttl_minutes=60):
        """Issue a single-use reset token: store its hash + expiry, return the
        raw token (to embed in the emailed link). The live password is untouched."""
        import secrets
        from datetime import timedelta
        raw = secrets.token_urlsafe(32)
        self.reset_token_hash = generate_password_hash(raw)
        self.reset_token_expires = local_now() + timedelta(minutes=ttl_minutes)
        return raw

    def check_reset_token(self, raw):
        """True if `raw` matches the stored, unexpired reset token."""
        if not raw or not self.reset_token_hash or not self.reset_token_expires:
            return False
        if local_now() > self.reset_token_expires:
            return False
        return check_password_hash(self.reset_token_hash, raw)

    def clear_reset_token(self):
        self.reset_token_hash = None
        self.reset_token_expires = None

    @property
    def own_permissions(self):
        """The user's per-module OVERRIDES (not the group): {key: 'view'|'edit'|'none'}.

        'none' means "explicitly revoke this even if the group grants it". This is
        the raw stored map; the effective access is ``permission_map``.
        """
        import json
        if self.permissions:
            try:
                v = json.loads(self.permissions)
                if isinstance(v, dict):
                    return {k: lvl for k, lvl in v.items()
                            if lvl in ('view', 'edit', 'none')}
            except (ValueError, TypeError):
                pass
        return {}

    @property
    def permission_map(self):
        """Effective per-module access: {module_key: 'view'|'edit'}.

        The assigned permission group provides the base; the user's own overrides
        are layered on top (an override of 'none' revokes a group permission).
        With no group and no overrides, falls back to the legacy
        ``allowed_modules`` list.
        """
        import json
        base = {}
        grp = self.permission_group
        if grp is not None and grp.is_active is not False:   # None default => active
            base = dict(grp.permission_map)
        overrides = self.own_permissions
        for k, lvl in overrides.items():
            if lvl == 'none':
                base.pop(k, None)
            else:
                base[k] = ('edit' if lvl == 'edit' else 'view')
        if not grp and not overrides and self.allowed_modules:
            try:
                lst = json.loads(self.allowed_modules)
                if isinstance(lst, list):
                    lvl = 'view' if self.view_only else 'edit'
                    return {k: lvl for k in lst}
            except (ValueError, TypeError):
                pass
        return base

    def set_permissions(self, perm_map):
        """Store the per-user override map {key: 'view'|'edit'|'none'}."""
        import json
        clean = {k: v for k, v in (perm_map or {}).items()
                 if v in ('view', 'edit', 'none')}
        self.permissions = json.dumps(clean) if clean else None

    def module_level(self, key):
        """'view' / 'edit' / None for a module."""
        return self.permission_map.get(key)

    @property
    def module_list(self):
        """Module keys this user may access (any level)."""
        return list(self.permission_map.keys())

    def set_modules(self, keys):
        """Backward-compatible: grant full (edit) access on each key."""
        self.set_permissions({k: 'edit' for k in (keys or [])})

    @property
    def is_super_admin(self):
        return self.role == 'super_admin'
    
    @property
    def is_admin(self):
        return self.role in ('super_admin', 'admin')
    
    @property
    def is_teacher(self):
        return self.role == 'teacher'
    
    @property
    def can_manage_users(self):
        return self.role in ('super_admin', 'admin')
    
    def get_display_role(self):
        """Human-readable role name"""
        roles = {
            'super_admin': 'Super Admin',
            'admin': 'Admin', 
            'teacher': 'Teacher',
            'readonly': 'View Only'
        }
        return roles.get(self.role, self.role.title())
    
    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


class PermissionGroup(db.Model):
    """A named template of module permissions.

    Assigning a user to a group gives them the group's permissions as a base;
    per-user overrides (User.own_permissions) are then layered on top (a 'none'
    override revokes a group-granted permission). A group with a branch_id is
    only offered to / managed by that branch; a NULL branch_id is a central
    (school-wide) template usable everywhere.
    """
    __tablename__ = 'permission_groups'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(255))
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)
    permissions = db.Column(db.Text)   # JSON {module|module.sub: 'view'|'edit'}
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    branch = db.relationship('Branch')

    @property
    def permission_map(self):
        import json
        if self.permissions:
            try:
                v = json.loads(self.permissions)
                if isinstance(v, dict):
                    return {k: ('edit' if lvl == 'edit' else 'view')
                            for k, lvl in v.items() if lvl in ('view', 'edit')}
            except (ValueError, TypeError):
                pass
        return {}

    def set_permissions(self, perm_map):
        import json
        clean = {k: ('edit' if v == 'edit' else 'view')
                 for k, v in (perm_map or {}).items() if v in ('view', 'edit')}
        self.permissions = json.dumps(clean) if clean else None

    def __repr__(self):
        return f'<PermissionGroup {self.name}>'


class Teacher(db.Model):
    """Teacher profile linked to User"""
    __tablename__ = 'teachers'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    employee_id = db.Column(db.String(20), unique=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))

    # Permissions
    can_mark_attendance = db.Column(db.Boolean, default=True)
    can_enter_results = db.Column(db.Boolean, default=False)
    can_edit_results = db.Column(db.Boolean, default=False)
    can_view_student_details = db.Column(db.Boolean, default=True)
    can_print_reports = db.Column(db.Boolean, default=True)
    
    # Additional info
    qualification = db.Column(db.String(200))
    date_joined = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    class_assignments = db.relationship('TeacherClassAssignment', backref='teacher', 
                                        lazy='dynamic', cascade='all, delete-orphan')
    subject_assignments = db.relationship('TeacherSubjectAssignment', backref='teacher', 
                                          lazy='dynamic', cascade='all, delete-orphan')
    
    @staticmethod
    def generate_employee_id():
        """Generate unique employee ID"""
        last = Teacher.query.order_by(Teacher.id.desc()).first()
        num = (last.id + 1) if last else 1
        return f"TCH{num:04d}"
    
    def can_access_class(self, class_arm_assignment_id):
        """Check if teacher can access this class"""
        if self.class_assignments.filter_by(
            class_arm_assignment_id=class_arm_assignment_id,
            is_active=True
        ).first():
            return True
        return self.subject_assignments.filter_by(
            class_arm_assignment_id=class_arm_assignment_id,
            is_active=True
        ).first() is not None

    @property
    def form_class_ids(self):
        """class_arm_assignment_ids this teacher is the *form teacher* of."""
        return {a.class_arm_assignment_id for a in
                self.class_assignments.filter_by(is_active=True, is_form_teacher=True).all()}

    def is_form_teacher_of(self, class_arm_assignment_id):
        """True only where the teacher is the form teacher (attendance/parent comms)."""
        return class_arm_assignment_id in self.form_class_ids

    def __repr__(self):
        return f'<Teacher {self.user.full_name if self.user else "Unknown"}>'


class TeacherClassAssignment(db.Model):
    """Assign teacher as form teacher of a class"""
    __tablename__ = 'teacher_class_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    class_arm_assignment_id = db.Column(db.Integer, db.ForeignKey('class_arm_assignments.id'), nullable=False)
    is_form_teacher = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationship
    class_arm_assignment = db.relationship('ClassArmAssignment')
    
    __table_args__ = (
        db.UniqueConstraint('teacher_id', 'class_arm_assignment_id', name='uq_teacher_class'),
    )


class TeacherSubjectAssignment(db.Model):
    """Assign teacher to teach a subject in a specific class"""
    __tablename__ = 'teacher_subject_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    class_arm_assignment_id = db.Column(db.Integer, db.ForeignKey('class_arm_assignments.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    class_arm_assignment = db.relationship('ClassArmAssignment')
    subject = db.relationship('Subject')
    
    __table_args__ = (
        db.UniqueConstraint('teacher_id', 'class_arm_assignment_id', 'subject_id', 
                          name='uq_teacher_subject_class'),
    )
