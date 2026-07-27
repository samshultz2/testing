"""Central catalogue of every issuable academic document.

This is the single source of truth that maps a ``doc_type`` to:
  * a human label and a category (for grouping in the UI),
  * the *engine* that renders it (a design module exposing the standard
    interface), and
  * whether it is a designed document (school-selectable collection + verified).

Adding a new document type is a one-line entry here plus (optionally) a content
spec in the relevant engine — the render pipeline, template gallery, default
selection and verification all pick it up automatically.
"""
from models.models_graduate import GRADUATE_DOC_TYPES

# Engine identifiers → the module that renders that family.
ENGINE_TRANSCRIPT = 'transcript'
ENGINE_SLC = 'slc'
ENGINE_STATEMENT = 'statement'
ENGINE_CERTIFICATE = 'certificate'
ENGINE_LETTER = 'letter'          # themed formal letters / references
ENGINE_PROSE = 'prose'            # legacy prose docs handled by graduate_docs._body_for

# doc_type -> (label, category, engine)
# NOTE: labels for the original seven come from GRADUATE_DOC_TYPES for continuity.
CATALOG = {
    # --- Academic records -------------------------------------------------
    'transcript':      ('Academic Transcript',            'Academic Records', ENGINE_TRANSCRIPT),
    'statement':       ('Statement of Result',            'Academic Records', ENGINE_STATEMENT),
    'notification':    ('Result Notification Slip',       'Academic Records', ENGINE_PROSE),
    # --- Graduation & completion -----------------------------------------
    'slc':             ('School Leaving Certificate',     'Graduation & Completion', ENGINE_SLC),
    'graduation':      ('Graduation Certificate',         'Graduation & Completion', ENGINE_CERTIFICATE),
    'completion':      ('Completion Certificate',         'Graduation & Completion', ENGINE_CERTIFICATE),
    'attendance_cert': ('Attendance Certificate',         'Graduation & Completion', ENGINE_CERTIFICATE),
    # --- Character & behaviour -------------------------------------------
    'testimonial':     ('Testimonial / Character Certificate', 'Character & Behaviour', ENGINE_PROSE),
    'conduct':         ('Conduct Report',                 'Character & Behaviour', ENGINE_PROSE),
    'character_cert':  ('Character Certificate',          'Character & Behaviour', ENGINE_CERTIFICATE),
    # --- Recommendation & references -------------------------------------
    'recommendation':             ('Recommendation Letter',            'Recommendation & References', ENGINE_LETTER),
    'university_recommendation':  ('University Recommendation Letter',  'Recommendation & References', ENGINE_LETTER),
    'scholarship_recommendation': ('Scholarship Recommendation Letter', 'Recommendation & References', ENGINE_LETTER),
    'employment_recommendation':  ('Employment Recommendation Letter',  'Recommendation & References', ENGINE_LETTER),
    'reference':                  ('General Reference Letter',          'Recommendation & References', ENGINE_LETTER),
    # --- Admissions & enrollment -----------------------------------------
    'admission':       ('Admission Letter',               'Admissions & Enrollment', ENGINE_LETTER),
    'acceptance':      ('Acceptance Letter',              'Admissions & Enrollment', ENGINE_LETTER),
    'transfer':        ('Transfer Certificate',           'Admissions & Enrollment', ENGINE_LETTER),
    'withdrawal':      ('Withdrawal Certificate',         'Admissions & Enrollment', ENGINE_LETTER),
    'confirmation':    ('Student Confirmation Letter',    'Admissions & Enrollment', ENGINE_LETTER),
    # --- Administrative ---------------------------------------------------
    'fee_clearance':        ('Fee Clearance Certificate',        'Administrative', ENGINE_CERTIFICATE),
    'graduation_clearance': ('Graduation Clearance Certificate', 'Administrative', ENGINE_CERTIFICATE),
    # --- Awards & recognition --------------------------------------------
    'merit_award':      ('Merit Award Certificate',        'Awards & Recognition', ENGINE_CERTIFICATE),
    'best_graduating':  ('Best Graduating Student',        'Awards & Recognition', ENGINE_CERTIFICATE),
    'best_subject':     ('Best in Subject Certificate',    'Awards & Recognition', ENGINE_CERTIFICATE),
    'leadership_award': ('Leadership Award',               'Awards & Recognition', ENGINE_CERTIFICATE),
    'sports_award':     ('Sports Award',                   'Awards & Recognition', ENGINE_CERTIFICATE),
    'excellence_award': ('Academic Excellence Certificate', 'Awards & Recognition', ENGINE_CERTIFICATE),
}

# Category display order for the UI.
CATEGORY_ORDER = [
    'Academic Records', 'Graduation & Completion', 'Character & Behaviour',
    'Recommendation & References', 'Admissions & Enrollment', 'Awards & Recognition',
    'Administrative',
]

# Engines whose documents are designed (school-selectable collection + verified).
_DESIGNED_ENGINES = {ENGINE_TRANSCRIPT, ENGINE_SLC, ENGINE_STATEMENT,
                     ENGINE_CERTIFICATE, ENGINE_LETTER}


def label(doc_type):
    if doc_type in CATALOG:
        return CATALOG[doc_type][0]
    return GRADUATE_DOC_TYPES.get(doc_type, doc_type)


def category(doc_type):
    return CATALOG.get(doc_type, (None, 'Other', None))[1]


def engine(doc_type):
    return CATALOG.get(doc_type, (None, None, ENGINE_PROSE))[2]


def is_designed(doc_type):
    return engine(doc_type) in _DESIGNED_ENGINES


def designed_types():
    return [dt for dt in CATALOG if is_designed(dt)]


def by_category():
    """[(category, [(doc_type, label, is_designed), …]), …] in display order."""
    out = []
    for cat in CATEGORY_ORDER:
        items = [(dt, m[0], is_designed(dt)) for dt, m in CATALOG.items() if m[1] == cat]
        if items:
            out.append((cat, items))
    return out
