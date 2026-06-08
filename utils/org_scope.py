"""Section & stream scoping (Stage 4).

Some branch roles only oversee part of a branch:

* a **section** group — Principal (secondary = junior+senior) vs
  Headmaster (primary = nursery+primary);
* a **stream** — HOD Arts (Arts + Commercial) vs HOD Sciences (Science).

These narrow what a user sees *within* their branch. Users without a section /
stream (the default) are unaffected.
"""
from flask import session
from utils.helpers import get_active_term

from models import db, SchoolClass, StudentEnrollment, ClassArmAssignment

# user.section -> the class.section values it covers
SECTION_GROUPS = {
    'secondary': {'junior', 'senior'},
    'primary': {'nursery', 'primary'},
}
# user.stream -> the Student.stream / Subject.category values it covers
STREAM_GROUPS = {
    'arts': {'Arts', 'Commercial'},
    'science': {'Science'},
}


def allowed_sections():
    """Set of class sections in scope, or ``None`` for no restriction."""
    return SECTION_GROUPS.get(session.get('section'))


def allowed_streams():
    """Set of streams/subject categories in scope, or ``None``."""
    return STREAM_GROUPS.get(session.get('stream'))


def scope_classes(query, model=SchoolClass):
    """Filter a SchoolClass query to the sections in scope."""
    sections = allowed_sections()
    if sections:
        return query.filter(model.section.in_(sections))
    return query


def scope_subjects(query, model):
    """Filter a Subject query to the stream's categories (model has .category)."""
    streams = allowed_streams()
    if streams:
        return query.filter(model.category.in_(streams))
    return query


def scope_students(query, term=None):
    """Apply section (via current enrolment) and stream filters to a Student query."""
    from models import Student
    sections = allowed_sections()
    if sections:
        if term is None:
            from models import Term
            term = get_active_term()
        sub = (db.session.query(StudentEnrollment.student_id)
               .join(ClassArmAssignment,
                     StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
               .join(SchoolClass, ClassArmAssignment.class_id == SchoolClass.id)
               .filter(StudentEnrollment.is_active == True,
                       SchoolClass.section.in_(sections)))
        if term:
            sub = sub.filter(ClassArmAssignment.term_id == term.id)
        query = query.filter(Student.id.in_(sub))
    streams = allowed_streams()
    if streams:
        query = query.filter(Student.stream.in_(streams))
    return query


def set_session_org(user):
    """Record a user's section/stream in the session at login."""
    if user is None:
        session.pop('section', None)
        session.pop('stream', None)
        return
    session['section'] = user.section
    session['stream'] = user.stream
