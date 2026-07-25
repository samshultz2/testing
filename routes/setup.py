"""First-run setup wizard — a guided checklist that gets a freshly-onboarded
school going in a few clicks: session/term, classes, subjects, grading, staff
invites and the first students. Each step shows live status and links straight to
the right page; classes and subjects also have one-click "seed the standard set"
buttons so the common case really is a button or two.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request

from models import (db, AcademicSession, SchoolClass, Subject, Student, User,
                    Branch, GradeScale, StaffInvite)
from utils.access_control import admin_required
from utils.helpers import get_active_session, get_active_term
from utils.audit import log_action

setup_bp = Blueprint('setup', __name__, url_prefix='/setup')

# The standard Nigerian secondary structure and a core subject set — enough to
# start; the school edits/extends from the normal pages afterwards.
_STD_CLASSES = [
    ('JSS1', 1, 'junior'), ('JSS2', 2, 'junior'), ('JSS3', 3, 'junior'),
    ('SSS1', 4, 'senior'), ('SSS2', 5, 'senior'), ('SSS3', 6, 'senior'),
]
_CORE_SUBJECTS = [
    ('English Language', 'ENG', 'General', False),
    ('Mathematics', 'MTH', 'General', False),
    ('Civic Education', 'CIV', 'General', False),
    ('Biology', 'BIO', 'Science', True),
    ('Chemistry', 'CHE', 'Science', True),
    ('Physics', 'PHY', 'Science', True),
    ('Agricultural Science', 'AGR', 'Science', True),
    ('Economics', 'ECO', 'Commercial', False),
    ('Government', 'GOV', 'Arts', False),
    ('Literature in English', 'LIT', 'Arts', False),
    ('Geography', 'GEO', 'Arts', False),
    ('Computer Studies', 'CMP', 'General', True),
]


def _status():
    """Live checklist state — each step: key, title, blurb, done, count, the link
    to its full page, and (optionally) a one-click seed action."""
    have_session = bool(get_active_session())
    have_term = bool(get_active_term())
    n_classes = SchoolClass.query.count()
    n_subjects = Subject.query.filter(Subject.is_active.isnot(False)).count()
    n_students = Student.query.count()
    n_users = User.query.count()
    n_invites = StaffInvite.query.count()
    n_grades = GradeScale.query.count()
    n_branches = Branch.query.count()

    steps = [
        {'key': 'session', 'icon': 'calendar-days', 'title': 'Academic session & term',
         'blurb': 'Set the current session and term — results, fees and attendance all hang off this.',
         'done': have_session and have_term,
         'detail': ('Active term set' if have_term else ('Session set, add a term' if have_session else 'Not set')),
         'url': url_for('academics.sessions_list'), 'cta': 'Set up'},
        {'key': 'classes', 'icon': 'layer-group', 'title': 'Classes',
         'blurb': 'Create your classes (JSS1–SSS3). One click adds the standard set; edit as needed.',
         'done': n_classes > 0, 'detail': f'{n_classes} class(es)',
         'url': url_for('academics.classes_list'), 'cta': 'Manage classes',
         'seed': url_for('setup.seed_classes'), 'seed_label': 'Add standard classes'},
        {'key': 'subjects', 'icon': 'book', 'title': 'Subjects',
         'blurb': 'Add the subjects you teach. One click adds a core set; edit or extend anytime.',
         'done': n_subjects > 0, 'detail': f'{n_subjects} subject(s)',
         'url': url_for('subjects.subjects_list'), 'cta': 'Manage subjects',
         'seed': url_for('setup.seed_subjects'), 'seed_label': 'Add core subjects'},
        {'key': 'grades', 'icon': 'award', 'title': 'Grading scale',
         'blurb': 'Define your grade bands (A/B/C…) so report cards compute grades and remarks.',
         'done': n_grades > 0, 'detail': f'{n_grades} band(s)',
         'url': url_for('settings.grades_list'), 'cta': 'Set grades'},
        {'key': 'staff', 'icon': 'user-plus', 'title': 'Invite staff',
         'blurb': 'Generate a link and send it to your principals / HODs / teachers — they sign up, you approve.',
         'done': (n_users > 1 or n_invites > 0),
         'detail': (f'{n_invites} invite link(s)' if n_invites else f'{n_users} user(s)'),
         'url': url_for('staff_onboarding.invites'), 'cta': 'Create invite link'},
        {'key': 'students', 'icon': 'user-graduate', 'title': 'Add students',
         'blurb': 'Register your students (add one, or bulk-import a spreadsheet).',
         'done': n_students > 0, 'detail': f'{n_students} student(s)',
         'url': url_for('main.add_student'), 'cta': 'Add students'},
    ]
    done = sum(1 for s in steps if s['done'])
    return steps, done, len(steps), {'branches': n_branches}


@setup_bp.route('/')
@admin_required
def wizard():
    steps, done, total, extra = _status()
    return render_template('setup/wizard.html', steps=steps, done=done, total=total,
                           percent=round(100 * done / total) if total else 0,
                           branches_url=url_for('settings.branches'), extra=extra)


@setup_bp.route('/seed-classes', methods=['POST'])
@admin_required
def seed_classes():
    added = 0
    for name, level, section in _STD_CLASSES:
        if not SchoolClass.query.filter_by(name=name).first():
            db.session.add(SchoolClass(name=name, level=level, section=section))
            added += 1
    db.session.commit()
    log_action('setup.seed_classes', f'{added} classes')
    flash(f'Added {added} standard class(es).' if added else
          'All standard classes already exist.', 'success')
    return redirect(url_for('setup.wizard'))


@setup_bp.route('/seed-subjects', methods=['POST'])
@admin_required
def seed_subjects():
    added = 0
    for name, short, category, practical in _CORE_SUBJECTS:
        if not Subject.query.filter(db.func.lower(Subject.name) == name.lower()).first():
            db.session.add(Subject(name=name, short_name=short, category=category,
                                   has_practical=practical, is_active=True))
            added += 1
    db.session.commit()
    log_action('setup.seed_subjects', f'{added} subjects')
    flash(f'Added {added} core subject(s).' if added else
          'All core subjects already exist.', 'success')
    return redirect(url_for('setup.wizard'))
