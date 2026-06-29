"""SQLAlchemy models — generator (split from the former models/models.py).
Base names (db, local_now, EncryptedString, …) come from the package __init__;
sibling models are referenced lazily inside methods as in the original."""
from models.models import *  # noqa: F401,F403


class GenTeacher(db.Model):
    """Teachers for timetable generation"""
    __tablename__ = 'gen_teachers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    staff_id = db.Column(db.String(20))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    school_level = db.Column(db.String(10), default='sss')  # 'jss' or 'sss'
    max_periods_per_day = db.Column(db.Integer, default=6)
    max_periods_per_week = db.Column(db.Integer, default=30)
    preferred_time = db.Column(db.String(20), default='any')  # 'morning', 'afternoon', 'any'
    is_part_time = db.Column(db.Boolean, default=False)
    available_days = db.Column(db.String(20))  # Comma-separated: "0,1,2,3,4" for Mon-Fri
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    subjects = db.relationship('GenTeacherSubject', backref='teacher', lazy='dynamic', cascade='all, delete-orphan')
    assignments = db.relationship('GenTeacherAssignment', backref='teacher', lazy='dynamic', cascade='all, delete-orphan')
    availability = db.relationship('GenTeacherAvailability', backref='teacher', lazy='dynamic', cascade='all, delete-orphan')
    
    @property
    def available_days_list(self):
        if self.available_days:
            return [int(d) for d in self.available_days.split(',') if d.strip()]
        return [0, 1, 2, 3, 4]  # Default all days
    
    def __repr__(self):
        return f'<GenTeacher {self.name}>'


class GenTeacherAvailability(db.Model):
    """Teacher availability - which periods they're NOT available"""
    __tablename__ = 'gen_teacher_availability'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('gen_teachers.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday to 4=Friday
    period_number = db.Column(db.Integer, nullable=False)
    is_available = db.Column(db.Boolean, default=False)  # False = NOT available
    reason = db.Column(db.String(100))  # Optional reason
    
    __table_args__ = (db.UniqueConstraint('teacher_id', 'day_of_week', 'period_number'),)


class GenTeacherSubject(db.Model):
    """Subjects a teacher can teach"""
    __tablename__ = 'gen_teacher_subjects'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('gen_teachers.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'), nullable=False)
    
    # Relationship to get subject details
    subject = db.relationship('GenSubject')
    
    __table_args__ = (db.UniqueConstraint('teacher_id', 'subject_id'),)


class GenSubjectConfig(db.Model):
    """Subject configuration for timetable generation - GLOBAL defaults"""
    __tablename__ = 'gen_subject_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'), nullable=False)  # Changed to gen_subjects
    school_level = db.Column(db.String(10), default='sss')  # 'jss' or 'sss'
    periods_per_week = db.Column(db.Integer, default=4)  # Default periods
    needs_double_period = db.Column(db.Boolean, default=False)
    double_period_count = db.Column(db.Integer, default=0)  # How many double periods
    preferred_time = db.Column(db.String(20), default='any')  # 'morning', 'afternoon', 'any'
    category = db.Column(db.String(20), default='core')  # 'core', 'science', 'arts', 'commercial'
    not_first_period = db.Column(db.Boolean, default=False)
    not_last_period = db.Column(db.Boolean, default=False)
    color = db.Column(db.String(7), default='#4472C4')  # Hex color for display
    room_id = db.Column(db.Integer, db.ForeignKey('gen_rooms.id'))  # Required room/lab
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationship
    subject = db.relationship('GenSubject')
    room = db.relationship('GenRoom')
    
    __table_args__ = (db.UniqueConstraint('subject_id', 'school_level'),)


class GenSubject(db.Model):
    """Subjects for timetable generation - separate from academic subjects"""
    __tablename__ = 'gen_subjects'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    short_name = db.Column(db.String(20))
    school_level = db.Column(db.String(10), default='sss')  # 'jss' or 'sss'
    category = db.Column(db.String(50))  # Science, Arts, Commercial, General, Vocational
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    __table_args__ = (db.UniqueConstraint('name', 'school_level'),)
    
    def __repr__(self):
        return f'<GenSubject {self.name} ({self.school_level})>'


class GenClassSubjectConfig(db.Model):
    """Per-class subject configuration - overrides global defaults"""
    __tablename__ = 'gen_class_subject_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    class_config_id = db.Column(db.Integer, db.ForeignKey('gen_class_configs.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'), nullable=False)
    is_enabled = db.Column(db.Boolean, default=True)  # Does this class take this subject?
    periods_per_week = db.Column(db.Integer, default=4)
    needs_double_period = db.Column(db.Boolean, default=False)
    double_period_count = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    class_config = db.relationship('GenClassConfig', backref='subject_configs')
    subject = db.relationship('GenSubject')
    
    __table_args__ = (db.UniqueConstraint('class_config_id', 'subject_id'),)


class GenRoom(db.Model):
    """Rooms/Venues for timetable generation"""
    __tablename__ = 'gen_rooms'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    short_name = db.Column(db.String(10))
    room_type = db.Column(db.String(20), default='classroom')  # classroom, lab, hall, field
    capacity = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    def __repr__(self):
        return f'<GenRoom {self.name}>'


class GenStream(db.Model):
    """Stream definitions (Science, Arts, Commercial)"""
    __tablename__ = 'gen_streams'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    short_name = db.Column(db.String(10))
    description = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    subjects = db.relationship('GenStreamSubject', backref='stream', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<GenStream {self.name}>'


class GenStreamSubject(db.Model):
    """Subjects belonging to each stream with stream-specific period configuration"""
    __tablename__ = 'gen_stream_subjects'
    
    id = db.Column(db.Integer, primary_key=True)
    stream_id = db.Column(db.Integer, db.ForeignKey('gen_streams.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'), nullable=False)
    is_compulsory = db.Column(db.Boolean, default=True)  # Compulsory within stream
    
    # Stream-specific period configuration (overrides global subject config)
    periods_per_week = db.Column(db.Integer, nullable=True)  # If NULL, use global config
    needs_double_period = db.Column(db.Boolean, nullable=True)  # If NULL, use global config
    double_period_count = db.Column(db.Integer, nullable=True)  # If NULL, use global config
    
    # Relationship
    subject = db.relationship('GenSubject')
    
    __table_args__ = (db.UniqueConstraint('stream_id', 'subject_id'),)


class GenClassConfig(db.Model):
    """Class configuration for generation"""
    __tablename__ = 'gen_class_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    class_name = db.Column(db.String(20), nullable=False)  # SSS1, SSS2, SSS3, JSS1, JSS2, JSS3
    school_level = db.Column(db.String(10), default='sss')  # 'jss' or 'sss'
    num_arms = db.Column(db.Integer, default=1)
    arm_names = db.Column(db.String(200))  # Comma-separated: "Iris,Rose,Lily,Tulip"
    has_streams = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    arm_streams = db.relationship('GenClassArmStream', backref='class_config', lazy='dynamic', cascade='all, delete-orphan')
    
    @property
    def arm_list(self):
        """Return list of arm names"""
        if self.arm_names:
            return [a.strip() for a in self.arm_names.split(',')]
        return []
    
    def __repr__(self):
        return f'<GenClassConfig {self.class_name}>'


class GenClassArmStream(db.Model):
    """Which stream each class arm belongs to"""
    __tablename__ = 'gen_class_arm_streams'
    
    id = db.Column(db.Integer, primary_key=True)
    class_config_id = db.Column(db.Integer, db.ForeignKey('gen_class_configs.id'), nullable=False)
    arm_name = db.Column(db.String(50), nullable=False)  # e.g., "Iris"
    stream_id = db.Column(db.Integer, db.ForeignKey('gen_streams.id'))
    
    # Relationship
    stream = db.relationship('GenStream')
    
    __table_args__ = (db.UniqueConstraint('class_config_id', 'arm_name'),)


class GenClassStreamSubject(db.Model):
    """Class-specific stream subject period configuration
    Allows SSS2 Science to have different periods than SSS3 Science for the same subject
    """
    __tablename__ = 'gen_class_stream_subjects'
    
    id = db.Column(db.Integer, primary_key=True)
    class_config_id = db.Column(db.Integer, db.ForeignKey('gen_class_configs.id'), nullable=False)
    stream_id = db.Column(db.Integer, db.ForeignKey('gen_streams.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'), nullable=False)
    
    # Class-stream specific period configuration
    periods_per_week = db.Column(db.Integer, nullable=False)
    needs_double_period = db.Column(db.Boolean, default=False)
    double_period_count = db.Column(db.Integer, default=0)
    is_enabled = db.Column(db.Boolean, default=True)  # Can disable subject for this class-stream
    
    # Relationships
    class_config = db.relationship('GenClassConfig')
    stream = db.relationship('GenStream')
    subject = db.relationship('GenSubject')
    
    __table_args__ = (db.UniqueConstraint('class_config_id', 'stream_id', 'subject_id'),)


class GenTeacherAssignment(db.Model):
    """Which teacher teaches which subject to which class-arm"""
    __tablename__ = 'gen_teacher_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('gen_teachers.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'), nullable=False)
    class_config_id = db.Column(db.Integer, db.ForeignKey('gen_class_configs.id'), nullable=False)
    arm_name = db.Column(db.String(50))  # Specific arm, or NULL for all arms
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    subject = db.relationship('GenSubject')
    class_config = db.relationship('GenClassConfig')
    
    __table_args__ = (db.UniqueConstraint('teacher_id', 'subject_id', 'class_config_id', 'arm_name'),)


class GenTimetableRule(db.Model):
    """Timetable generation rules"""
    __tablename__ = 'gen_timetable_rules'
    
    id = db.Column(db.Integer, primary_key=True)
    rule_type = db.Column(db.String(50), nullable=False)
    # Types: 'no_repeat_same_day', 'max_consecutive', 'break_after_period', etc.
    value = db.Column(db.String(100))
    school_level = db.Column(db.String(10), default='sss')  # 'jss' or 'sss'
    subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'))  # If rule is subject-specific
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationship
    subject = db.relationship('GenSubject')


class GenTimetableResult(db.Model):
    """Generated timetable results"""
    __tablename__ = 'gen_timetable_results'
    
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.String(50), nullable=False)  # Groups results from same generation
    school_level = db.Column(db.String(10), default='sss')  # 'jss' or 'sss'
    class_name = db.Column(db.String(20), nullable=False)
    arm_name = db.Column(db.String(50), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday to 4=Friday
    period_number = db.Column(db.Integer, nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'))
    teacher_id = db.Column(db.Integer, db.ForeignKey('gen_teachers.id'))
    room_id = db.Column(db.Integer, db.ForeignKey('gen_rooms.id'))
    is_double_period = db.Column(db.Boolean, default=False)
    is_locked = db.Column(db.Boolean, default=False)  # Locked slots won't change on regeneration
    generated_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    subject = db.relationship('GenSubject')
    teacher = db.relationship('GenTeacher')
    room = db.relationship('GenRoom')
    
    @property
    def day_name(self):
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        return days[self.day_of_week] if 0 <= self.day_of_week < 5 else ''


class ActiveTimetableBatch(db.Model):
    """The generated timetable batch currently marked 'in use' (published live)
    for a branch + school level. One row per (branch, level)."""
    __tablename__ = 'active_timetable_batches'

    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    school_level = db.Column(db.String(10), default='sss')   # 'jss' or 'sss'
    batch_id = db.Column(db.String(50), nullable=False)
    set_at = db.Column(db.DateTime, default=local_now)
    set_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    __table_args__ = (
        db.UniqueConstraint('branch_id', 'school_level', name='uq_active_timetable_branch_level'),
    )

    @staticmethod
    def active_batch_id(branch_id, level):
        # Defensive: on a database whose schema predates this table (e.g. an
        # Alembic deployment that hasn't run the migration yet), reading must not
        # break the page — just report 'no batch in use' until the table exists.
        try:
            row = ActiveTimetableBatch.query.filter_by(branch_id=branch_id, school_level=level).first()
            return row.batch_id if row else None
        except Exception:
            db.session.rollback()
            return None

    @staticmethod
    def set_active(branch_id, level, batch_id, user_id=None):
        # Defensive (see active_batch_id): if the table doesn't exist yet, don't
        # fail the publish that already happened — just skip recording the marker.
        try:
            row = ActiveTimetableBatch.query.filter_by(branch_id=branch_id, school_level=level).first()
            if not row:
                row = ActiveTimetableBatch(branch_id=branch_id, school_level=level)
                db.session.add(row)
            row.batch_id = batch_id
            row.set_at = local_now()
            row.set_by_user_id = user_id
            return True
        except Exception:
            db.session.rollback()
            return False


class GenSettings(db.Model):
    """Generator settings including school info for printing"""
    __tablename__ = 'gen_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(50), nullable=False, unique=True)
    setting_value = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=local_now)
    
    @staticmethod
    def get(key, default=None):
        setting = GenSettings.query.filter_by(setting_key=key).first()
        return setting.setting_value if setting else default
    
    @staticmethod
    def set(key, value):
        setting = GenSettings.query.filter_by(setting_key=key).first()
        if setting:
            setting.setting_value = value
        else:
            setting = GenSettings(setting_key=key, setting_value=value)
            db.session.add(setting)
        db.session.commit()


class GenSubjectClashRule(db.Model):
    """
    Rules for subjects that must NOT be scheduled at the same time.
    Used for combined classes where different student groups take different subjects simultaneously.
    Example: Geography for SSS3 Iris should not clash with Literature (because Arts students do Lit while Commercial do Geo)
    """
    __tablename__ = 'gen_subject_clash_rules'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # Descriptive name for the rule
    description = db.Column(db.Text)  # Explanation of why this rule exists
    
    # Source subject (the one we're protecting)
    source_subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'), nullable=False)
    source_class_name = db.Column(db.String(20), nullable=False)  # e.g., "SSS3"
    source_arm_name = db.Column(db.String(50))  # e.g., "Iris", or NULL for all arms
    
    # Target subject (the one that must not clash with source)
    target_subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'), nullable=False)
    target_class_name = db.Column(db.String(20))  # e.g., "SSS1", or NULL for all classes
    target_arm_name = db.Column(db.String(50))  # e.g., "Iris", or NULL for all arms
    
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    source_subject = db.relationship('GenSubject', foreign_keys=[source_subject_id])
    target_subject = db.relationship('GenSubject', foreign_keys=[target_subject_id])
    
    def __repr__(self):
        return f'<GenSubjectClashRule {self.name}>'


class GenCombinedClassRule(db.Model):
    """
    Rules for combined classes where a teacher "shadows" another subject.
    When the shadow subject is scheduled, the teacher is also occupied.
    Used to ensure the teacher doesn't get 3 consecutive periods across both subjects.
    Example: Literature teacher shadows Geography for SSS3 Iris (same time slot)
    """
    __tablename__ = 'gen_combined_class_rules'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    
    # The subject being shadowed (e.g., Geography)
    shadow_subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'), nullable=False)
    shadow_class_name = db.Column(db.String(20), nullable=False)  # e.g., "SSS3"
    shadow_arm_name = db.Column(db.String(50))  # e.g., "Iris"
    
    # The teacher's own subject (e.g., Literature) - used to find the teacher
    teacher_subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'), nullable=False)
    teacher_class_name = db.Column(db.String(20), nullable=False)  # The class where teacher is assigned
    teacher_arm_name = db.Column(db.String(50))  # The arm where teacher is assigned
    
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    shadow_subject = db.relationship('GenSubject', foreign_keys=[shadow_subject_id])
    teacher_subject = db.relationship('GenSubject', foreign_keys=[teacher_subject_id])
    
    def __repr__(self):
        return f'<GenCombinedClassRule {self.name}>'
