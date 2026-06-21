"""
Fuzzy subject-name canonicalisation.

Scoresheets abbreviate subjects inconsistently ("Eng", "English", "English Lang",
"Maths", "F. Maths", "Econs", "CRS"...). This maps a free-text subject to the
canonical WAEC subject name, or ``None`` when nothing plausibly matches.
"""
import re

from utils.helpers import WAEC_SUBJECTS


def _norm(s):
    """Uppercase, drop punctuation, collapse whitespace."""
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Za-z0-9 ]+', ' ', (s or '').upper())).strip()


# Explicit aliases (normalised form -> canonical). Canonical names and a few
# systematic variants are added automatically below.
_ALIASES = {
    'ENG': 'English Language', 'ENGLISH': 'English Language',
    'ENG LANG': 'English Language', 'ENGLISH LANG': 'English Language',
    'USE OF ENGLISH': 'English Language',
    'MATH': 'Mathematics', 'MATHS': 'Mathematics', 'GEN MATHS': 'Mathematics',
    'GENERAL MATHS': 'Mathematics', 'GENERAL MATHEMATICS': 'Mathematics',
    'CORE MATHEMATICS': 'Mathematics',
    'F MATHS': 'Further Mathematics', 'FURTHER MATHS': 'Further Mathematics',
    'FMATHS': 'Further Mathematics', 'ADD MATHS': 'Further Mathematics',
    'ADDITIONAL MATHEMATICS': 'Further Mathematics', 'ELECTIVE MATHEMATICS': 'Further Mathematics',
    'PHY': 'Physics', 'PHYS': 'Physics',
    'CHEM': 'Chemistry',
    'BIO': 'Biology',
    'ECONS': 'Economics', 'ECON': 'Economics', 'ECO': 'Economics',
    'GOVT': 'Government', 'GOV': 'Government',
    'LIT': 'Literature in English', 'LITERATURE': 'Literature in English',
    'LIT IN ENG': 'Literature in English', 'LIT IN ENGLISH': 'Literature in English',
    'AGRIC': 'Agricultural Science', 'AGRIC SCIENCE': 'Agricultural Science',
    'AGRICULTURE': 'Agricultural Science', 'AGRIC SCI': 'Agricultural Science',
    'GEO': 'Geography', 'GEOG': 'Geography',
    'COMM': 'Commerce',
    'ACC': 'Accounting', 'ACCT': 'Accounting', 'ACCOUNTS': 'Accounting',
    'FINANCIAL ACCOUNTING': 'Accounting', 'PRINCIPLES OF ACCOUNTS': 'Accounting',
    'COMP': 'Computer Studies', 'COMPUTER': 'Computer Studies',
    'COMPUTER SCIENCE': 'Computer Studies', 'ICT': 'Computer Studies',
    'CIVIC': 'Civic Education', 'CIV ED': 'Civic Education', 'CIVIC ED': 'Civic Education',
    'CRS': 'Christian Religious Studies', 'CRK': 'Christian Religious Studies',
    'CHRISTIAN RELIGIOUS KNOWLEDGE': 'Christian Religious Studies',
    'CHRISTIAN REL STUDIES': 'Christian Religious Studies',
    'IRS': 'Islamic Religious Studies', 'IRK': 'Islamic Religious Studies',
    'ISLAMIC STUDIES': 'Islamic Religious Studies',
    'ISLAMIC RELIGIOUS KNOWLEDGE': 'Islamic Religious Studies',
    'FRE': 'French',
    'YOR': 'Yoruba', 'IGB': 'Igbo', 'HAU': 'Hausa',
    'HIST': 'History',
    'VA': 'Visual Arts', 'VISUAL ART': 'Visual Arts', 'FINE ART': 'Visual Arts',
    'FINE ARTS': 'Visual Arts', 'CREATIVE ARTS': 'Visual Arts',
    'MUS': 'Music',
    'TD': 'Technical Drawing', 'TECH DRAWING': 'Technical Drawing',
    'F N': 'Food and Nutrition', 'FOODS AND NUTRITION': 'Food and Nutrition',
    'HOME ECON': 'Home Economics', 'HOME ECO': 'Home Economics',
    'PHE': 'Physical Education', 'PE': 'Physical Education', 'PHYSICAL ED': 'Physical Education',
    'DATA PROC': 'Data Processing', 'DP': 'Data Processing',
    'DIGITAL TECH': 'Digital Technologies', 'DIGITAL TECHNOLOGY': 'Digital Technologies',
    'LIVESTOCK': 'Livestock Farming',
}

# Build the full normalised lookup: canonical names, their de-suffixed forms, and
# the explicit aliases above.
_LOOKUP = {}
for _canon in WAEC_SUBJECTS:
    _LOOKUP[_norm(_canon)] = _canon
    # also index the name with trailing qualifiers stripped ("English Language"
    # -> "ENGLISH", "Computer Studies" -> "COMPUTER", "Agricultural Science" -> "AGRICULTURAL")
    _base = re.sub(r' (LANGUAGE|STUDIES|SCIENCE|IN ENGLISH|FARMING)$', '', _norm(_canon)).strip()
    if _base and _base not in _LOOKUP:
        _LOOKUP[_base] = _canon
for _k, _v in _ALIASES.items():
    _LOOKUP[_norm(_k)] = _v


def canonical_subject(raw):
    """Return the canonical WAEC subject for *raw*, or ``None`` if unrecognised."""
    n = _norm(raw)
    if not n:
        return None
    if n in _LOOKUP:
        return _LOOKUP[n]
    # Unique prefix fallback (e.g. "ENGLISH LANG" vs "ENGLISH"); only accept when
    # exactly one canonical subject matches, so ambiguous input stays unresolved.
    hits = set()
    if len(n) >= 3:
        for key, c in _LOOKUP.items():
            if key.startswith(n) or n.startswith(key):
                hits.add(c)
    return next(iter(hits)) if len(hits) == 1 else None
