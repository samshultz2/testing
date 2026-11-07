"""One definition of the WAEC / NECO grading rules for every analytics page,
export and prediction — so "credit", "pass" and "5 credits including English
and Mathematics" mean exactly the same thing everywhere.

Import from here instead of re-declaring grade lists in a module.
"""
from __future__ import annotations

import re

WAEC_GRADES = ('A1', 'B2', 'B3', 'C4', 'C5', 'C6', 'D7', 'E8', 'F9')
DISTINCTION_GRADES = frozenset({'A1', 'B2', 'B3'})
CREDIT_GRADES = frozenset({'A1', 'B2', 'B3', 'C4', 'C5', 'C6'})      # "credit or better"
PASS_GRADES = CREDIT_GRADES                                          # WAEC "pass" = credit for admission
ORDINARY_PASS_GRADES = frozenset({'D7', 'E8'})
FAIL_GRADES = frozenset({'F9'})
NEAR_CREDIT_GRADES = frozenset({'D7'})                               # one grade short of a credit

# Higher-is-better points (A1 = 9 … F9 = 1) for averages.
GRADE_POINTS = {g: 9 - i for i, g in enumerate(WAEC_GRADES)}
# WAEC's own ordinal (A1 = 1 … F9 = 9), lower is better — for ranking / legacy.
GRADE_ORDINAL = {g: i + 1 for i, g in enumerate(WAEC_GRADES)}

BENCHMARK_CREDITS = 5          # admission benchmark: 5 credits incl. English and Maths


def norm_grade(g):
    return (g or '').strip().upper()


def is_credit(g):
    return norm_grade(g) in CREDIT_GRADES


def is_distinction(g):
    return norm_grade(g) in DISTINCTION_GRADES


def points(g):
    return GRADE_POINTS.get(norm_grade(g), 0)


# --------------------------------------------------------------------------- #
# Subjects
# --------------------------------------------------------------------------- #
_ALIASES = {
    'english': 'English Language', 'english language': 'English Language', 'use of english': 'English Language',
    'english studies': 'English Language', 'eng': 'English Language',
    'mathematics': 'Mathematics', 'maths': 'Mathematics', 'math': 'Mathematics',
    'general mathematics': 'Mathematics', 'gen maths': 'Mathematics',
    'further maths': 'Further Mathematics', 'further mathematics': 'Further Mathematics',
    'literature': 'Literature in English', 'literature in english': 'Literature in English',
    'lit in english': 'Literature in English',
    'crs': 'Christian Religious Studies', 'c.r.s': 'Christian Religious Studies',
    'christian religious knowledge': 'Christian Religious Studies', 'crk': 'Christian Religious Studies',
    'irs': 'Islamic Religious Studies', 'irk': 'Islamic Religious Studies',
    'agric': 'Agricultural Science', 'agriculture': 'Agricultural Science',
    'agricultural science': 'Agricultural Science',
    'civic': 'Civic Education', 'civic education': 'Civic Education',
    'computer': 'Data Processing', 'computer studies': 'Computer Studies',
    'accounting': 'Financial Accounting', 'financial accounting': 'Financial Accounting',
    'econs': 'Economics', 'govt': 'Government', 'geog': 'Geography',
    'bio': 'Biology', 'chem': 'Chemistry', 'phy': 'Physics',
}


def canonical_subject(name):
    """Display name with aliases folded ("Maths" → "Mathematics"), using the
    app's fuzzy subject matcher first (utils.subject_match), then a small local
    alias list; unknown names come back tidied but unchanged."""
    try:
        from utils.subject_match import canonical_subject as _fuzzy
        hit = _fuzzy(name)
        if hit:
            return hit
    except Exception:  # pragma: no cover
        pass
    s = ' '.join(re.sub(r'[^A-Za-z0-9 ]+', ' ', name or '').split())
    return _ALIASES.get(s.lower(), s)


def subject_key(name):
    """Normalised comparison key for a subject name (canonical, lower-case)."""
    return ' '.join(re.sub(r'[^a-z0-9 ]+', ' ', canonical_subject(name).lower()).split())


def core_key(subject):
    k = subject_key(subject)
    if k.startswith('english'):
        return 'english'
    if k == 'mathematics':
        return 'mathematics'
    return None


def is_core(subject):
    return core_key(subject) is not None


def five_credit_status(grades_by_subject, benchmark=BENCHMARK_CREDITS):
    """{'credits', 'english', 'maths', 'meets', 'near'} for one sitting —
    ``grades_by_subject`` is {subject: grade}. ``near`` = would meet the
    benchmark if one D7 were a C6 (the "one grade short" group)."""
    credits = sum(1 for g in grades_by_subject.values() if is_credit(g))
    eng = any(core_key(s) == 'english' and is_credit(g) for s, g in grades_by_subject.items())
    mth = any(core_key(s) == 'mathematics' and is_credit(g) for s, g in grades_by_subject.items())
    meets = eng and mth and credits >= benchmark
    near = False
    if not meets:
        for s, g in grades_by_subject.items():
            if norm_grade(g) not in NEAR_CREDIT_GRADES:
                continue
            ck = core_key(s)
            e2, m2 = eng or ck == 'english', mth or ck == 'mathematics'
            if e2 and m2 and credits + 1 >= benchmark:
                near = True
                break
    return {'credits': credits, 'english': eng, 'maths': mth, 'meets': meets, 'near': near}
