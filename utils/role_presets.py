"""Role presets — the school hierarchy as one-click access bundles.

A preset just *pre-fills* the user form (underlying role, branch scope and the
module checkboxes); an admin can still tweak the result. Presets are plain data,
so another school can edit this dict (or ignore it and build custom users).

Each preset:
    label       human name shown in the dropdown
    role        underlying User.role (admin bypasses module gates entirely)
    scope       'central' (all branches) or 'branch' (their own)
    modules     module keys to tick (ignored for admin role = full access)
    section     optional level group this role oversees (Stage 4 filtering)
    stream      optional subject group (Stage 4 filtering)
    description short help text
"""

# Module bundles reused below.
_ACADEMIC = ['students', 'academics', 'attendance', 'results', 'external_exams',
             'cbt', 'timetable', 'events', 'promotion', 'reports']
_EXAMS = ['academics', 'results', 'external_exams', 'cbt', 'reports', 'students',
          'promotion']
_HOD = ['results', 'external_exams', 'cbt', 'students', 'reports']

ROLE_PRESETS = {
    # ---- Central (cross-branch) ----
    'director_of_studies': {
        'label': 'Director of Studies',
        'role': 'admin', 'scope': 'central', 'modules': [],
        'description': 'Unfiltered access across every branch.',
    },
    'exams_standards': {
        'label': 'Exams & Standards',
        'role': 'staff', 'scope': 'central', 'modules': _EXAMS,
        'description': 'Academic & exam oversight across all branches.',
    },
    'it_department': {
        'label': 'IT Department',
        'role': 'admin', 'scope': 'central', 'modules': [],
        'description': 'System administration (users, settings) across branches.',
    },
    # ---- Branch ----
    'principal': {
        'label': 'Principal (Secondary)',
        'role': 'staff', 'scope': 'branch', 'modules': _ACADEMIC + ['communication', 'hr'],
        'section': 'secondary',
        'description': 'Heads JSS + SSS for one branch.',
    },
    'headmaster': {
        'label': 'Headmaster / Headmistress (Nursery & Primary)',
        'role': 'staff', 'scope': 'branch', 'modules': _ACADEMIC + ['communication', 'hr'],
        'section': 'primary',
        'description': 'Heads Nursery + Primary for one branch.',
    },
    'hod_arts': {
        'label': 'HOD — Arts & Commercial',
        'role': 'staff', 'scope': 'branch', 'modules': _HOD,
        'stream': 'arts',
        'description': 'Heads Arts/Commercial subjects for one branch.',
    },
    'hod_sciences': {
        'label': 'HOD — Sciences',
        'role': 'staff', 'scope': 'branch', 'modules': _HOD,
        'stream': 'science',
        'description': 'Heads Science subjects for one branch.',
    },
    'headteacher': {
        'label': 'Headteacher',
        'role': 'staff', 'scope': 'branch',
        'modules': ['students', 'attendance', 'results', 'cbt', 'timetable', 'events'],
        'description': 'Section head / coordinator for one branch.',
    },
    'teacher': {
        'label': 'Teacher',
        'role': 'teacher', 'scope': 'branch', 'modules': [],
        'description': 'Class/subject teacher (limited to assigned classes).',
    },
    'bursar': {
        'label': 'Bursar',
        'role': 'staff', 'scope': 'branch',
        'modules': ['finance', 'communication'],
        'description': 'Fees, expenses and sales for one branch.',
    },
}


def presets_for_form():
    """Compact dict the user form embeds as JSON to pre-fill fields."""
    return {k: {'role': p['role'], 'scope': p['scope'], 'modules': p['modules'],
                'label': p['label'], 'description': p.get('description', '')}
            for k, p in ROLE_PRESETS.items()}
