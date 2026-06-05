"""
Enhanced User Models for PosyHub
Includes User, Teacher, TeacherAssignment models for role-based access
"""
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from models import db


def local_now():
    return datetime.now()


class User(db.Model):
    """Enhanced User accounts for the system with role-based access"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    
    # Role: super_admin, admin, teacher, readonly
    role = db.Column(db.String(20), default='teacher')
    
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Relationships
    teacher_profile = db.relationship('Teacher', backref='user', uselist=False, cascade='all, delete-orphan')
    created_by = db.relationship('User', remote_side=[id], backref='created_users')
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password_hash, password)
    
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
    
    @property
    def can_enter_results(self):
        """Check if user can enter results (admin or teacher with permission)"""
        if self.is_admin:
            return True
        if self.is_teacher and self.teacher_profile:
            return self.teacher_profile.can_enter_results
        return False
    
    @property
    def can_view_all_classes(self):
        """Admins can view all, teachers only their assigned classes"""
        return self.is_admin
    
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


class Teacher(db.Model):
    """Teacher profile linked to User"""
    __tablename__ = 'teachers'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    employee_id = db.Column(db.String(20), unique=True)  # Staff ID
    
    # Permissions
    can_mark_attendance = db.Column(db.Boolean, default=True)
    can_enter_results = db.Column(db.Boolean, default=False)  # Admin must enable
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
    
    def is_form_teacher_of(self, class_arm_assignment_id):
        """Check if teacher is form teacher of this class"""
        return self.class_assignments.filter_by(
            class_arm_assignment_id=class_arm_assignment_id,
            is_form_teacher=True,
            is_active=True
        ).first() is not None
    
    def teaches_class(self, class_arm_assignment_id):
        """Check if teacher teaches any subject in this class"""
        return self.subject_assignments.filter_by(
            class_arm_assignment_id=class_arm_assignment_id,
            is_active=True
        ).first() is not None
    
    def get_form_classes(self):
        """Get all classes where this teacher is form teacher"""
        return [a.class_arm_assignment for a in self.class_assignments.filter_by(
            is_form_teacher=True, is_active=True
        ).all()]
    
    def get_teaching_subjects(self, class_arm_assignment_id=None):
        """Get subjects this teacher teaches, optionally filtered by class"""
        query = self.subject_assignments.filter_by(is_active=True)
        if class_arm_assignment_id:
            query = query.filter_by(class_arm_assignment_id=class_arm_assignment_id)
        return query.all()
    
    def can_access_class(self, class_arm_assignment_id):
        """Check if teacher can access this class (form teacher or teaches there)"""
        if self.is_form_teacher_of(class_arm_assignment_id):
            return True
        return self.teaches_class(class_arm_assignment_id)
    
    def can_enter_subject_results(self, class_arm_assignment_id, subject_id):
        """Check if teacher can enter results for this subject in this class"""
        if not self.can_enter_results:
            return False
        return self.subject_assignments.filter_by(
            class_arm_assignment_id=class_arm_assignment_id,
            subject_id=subject_id,
            is_active=True
        ).first() is not None
    
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
    
    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('teacher_id', 'class_arm_assignment_id', name='uq_teacher_class'),
    )
    
    def __repr__(self):
        return f'<TeacherClassAssignment {self.teacher_id} -> {self.class_arm_assignment_id}>'


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
    
    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('teacher_id', 'class_arm_assignment_id', 'subject_id', 
                          name='uq_teacher_subject_class'),
    )
    
    def __repr__(self):
        return f'<TeacherSubjectAssignment {self.teacher_id} teaches {self.subject_id} in {self.class_arm_assignment_id}>'


# Helper functions for access control
def get_user_accessible_classes(user):
    """Get list of class_arm_assignment_ids user can access"""
    from models import ClassArmAssignment, Term
    
    if user.is_admin:
        # Admins can access all classes
        active_term = Term.query.filter_by(is_active=True).first()
        if active_term:
            return [a.id for a in ClassArmAssignment.query.filter_by(term_id=active_term.id).all()]
        return []
    
    if user.is_teacher and user.teacher_profile:
        teacher = user.teacher_profile
        accessible = set()
        
        # Form teacher classes
        for assignment in teacher.class_assignments.filter_by(is_active=True).all():
            accessible.add(assignment.class_arm_assignment_id)
        
        # Subject teaching classes
        for assignment in teacher.subject_assignments.filter_by(is_active=True).all():
            accessible.add(assignment.class_arm_assignment_id)
        
        return list(accessible)
    
    return []


def user_can_access_class(user, class_arm_assignment_id):
    """Check if user can access a specific class"""
    if user.is_admin:
        return True
    if user.is_teacher and user.teacher_profile:
        return user.teacher_profile.can_access_class(class_arm_assignment_id)
    return False


def user_can_enter_results_for(user, class_arm_assignment_id, subject_id):
    """Check if user can enter results for a subject in a class"""
    if user.is_admin:
        return True
    if user.is_teacher and user.teacher_profile:
        return user.teacher_profile.can_enter_subject_results(class_arm_assignment_id, subject_id)
    return False
