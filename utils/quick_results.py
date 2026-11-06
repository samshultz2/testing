"""Quick results entry: one line per candidate, comma-separated.

    John Caleb Matthew, Eng A1, Maths B2, Biology C4
    Ada Obi, English B, Maths A, Basic Science C        (JSS3 / Basic 6)

The first field is the candidate's name (any order, middle name optional —
matched against the roster with the same fuzzy matcher as the WAEC paste/scan
flows). Every following field is a subject followed by its grade (``Eng A1``,
``Eng: A1``, ``Eng - A1``, ``Eng=A1``). For exams that publish scores (JSS3 /
Basic 6) a number is accepted in place of the grade and graded with the
configured bands (``Maths 72``).

Grades are validated against the exam's own scheme, so a WAEC grade such as
``A1`` typed into a JSS3 / Basic 6 entry is rejected with a hint that those
exams use plain letters (A, B, C, P, F), and vice versa.

The parser is exam-agnostic: the caller passes a subject resolver and a grade
parser (see ``waec_spec`` / ``school_exam_spec``).
"""
from __future__ import annotations

import re

_NUM = re.compile(r'^\d+(?:\.\d+)?$')


def _split_line(line):
    """Split a line into fields on commas (and semicolons / tabs)."""
    return [f.strip() for f in re.split(r'[,;\t]', line) if f.strip()]


def _split_field(field):
    """'Eng A1' / 'Eng: A1' / 'Basic Science - B' / 'Maths=72' → (subject, value).
    The value is the last token; everything before it is the subject."""
    f = field.strip().rstrip('.')
    m = re.match(r'^(.*?)\s*(?:[:=]|\s[-–]\s|\s)\s*([A-Za-z]\d?[+]?|\d+(?:\.\d+)?)$', f)
    if not m or not m.group(1).strip():
        return None, None
    return m.group(1).strip(' :-=–'), m.group(2).strip()


def parse_quick_lines(text, students, spec):
    """Parse quick-entry text against ``students`` using ``spec``.

    ``spec`` is a dict with:
      * ``resolve_subject(raw) -> canonical | None``
      * ``parse_value(raw) -> (score|None, grade|None, error|None)``
      * ``label`` (e.g. 'WAEC') used in messages

    Returns ``{'rows': [...], 'n_ready': rows_with_results, 'n_results': results}``.
    Each row: ``line``, ``raw``, ``name``, ``student`` (or None), ``score`` (match
    confidence), ``items`` [(subject, score, grade, raw_field)], ``errors`` [str].
    """
    from utils.waec_ocr import match_students_unique
    lines = [(i, ln.strip()) for i, ln in enumerate((text or '').splitlines(), 1) if ln.strip()]
    parsed = []
    for ln_no, raw in lines:
        fields = _split_line(raw)
        if not fields:
            continue
        name, rest = fields[0], fields[1:]
        row = {'line': ln_no, 'raw': raw, 'name': name, 'student': None, 'score': 0.0,
               'items': [], 'errors': []}
        seen = set()
        for fld in rest:
            subj_raw, val = _split_field(fld)
            if not subj_raw:
                row['errors'].append(f'"{fld}" — expected a subject then a grade, e.g. "Eng A".')
                continue
            subject = spec['resolve_subject'](subj_raw)
            if not subject:
                row['errors'].append(f'"{subj_raw}" is not a recognised {spec["label"]} subject.')
                continue
            score, grade, err = spec['parse_value'](val)
            if err:
                row['errors'].append(f'{subject}: {err}')
                continue
            if subject in seen:
                row['errors'].append(f'{subject} appears twice — the last one is used.')
                row['items'] = [it for it in row['items'] if it[0] != subject]
            seen.add(subject)
            row['items'].append((subject, score, grade, fld))
        if not rest:
            row['errors'].append('No subjects — write the name, then e.g. ", Eng A, Maths B".')
        parsed.append(row)

    matches = match_students_unique([r['name'] for r in parsed], students)
    for row, (st, sc) in zip(parsed, matches):
        row['student'], row['score'] = st, sc
        if st is None:
            row['errors'].insert(0, f'No {spec["label"]} candidate matches "{row["name"]}".')
    ready = [r for r in parsed if r['student'] is not None and r['items']]
    return {'rows': parsed, 'n_ready': len(ready), 'n_results': sum(len(r['items']) for r in ready)}


# --------------------------------------------------------------------------- #
# WAEC (SSS3): grades A1 … F9 only
# --------------------------------------------------------------------------- #
def waec_spec():
    from utils.subject_match import canonical_subject
    from utils.helpers import WAEC_GRADES

    def parse_value(v):
        g = (v or '').strip().upper()
        if g in WAEC_GRADES:
            return None, g, None
        if _NUM.match(g):
            return None, None, f'"{v}" — WAEC results are grades (A1 … F9), not scores.'
        if g in ('A', 'B', 'C', 'D', 'E', 'F', 'P'):
            return None, None, (f'"{v}" is not a WAEC grade — use A1, B2, B3, C4, C5, C6, '
                                f'D7, E8 or F9.')
        return None, None, f'"{v}" is not a valid WAEC grade (A1 … F9).'

    return {'label': 'SSS3 / WAEC', 'resolve_subject': canonical_subject,
            'parse_value': parse_value}


# --------------------------------------------------------------------------- #
# JSS3 / Basic 6: plain letters from the configured bands (or a score)
# --------------------------------------------------------------------------- #
# Extra abbreviations common on JSS / primary result sheets.
_SCHOOL_ALIASES = {
    'ENG': 'english', 'ENGLISH': 'english', 'ENG LANG': 'english', 'ENG STUDIES': 'english',
    'MATH': 'mathematics', 'MATHS': 'mathematics', 'MTH': 'mathematics',
    'BSC': 'basic science', 'B SCI': 'basic science', 'BASIC SCI': 'basic science',
    'BTECH': 'basic technology', 'B TECH': 'basic technology', 'BT': 'basic technology',
    'BASIC TECH': 'basic technology',
    'BST': 'basic science and technology',
    'SOS': 'social studies', 'SST': 'social studies', 'SOCIAL': 'social studies',
    'CIVIC': 'civic education', 'CIV': 'civic education', 'CIV ED': 'civic education',
    'CCA': 'cultural and creative arts', 'CREATIVE ARTS': 'cultural and creative arts',
    'CRS': 'christian religious studies', 'CRK': 'christian religious studies',
    'IRS': 'islamic studies', 'IRK': 'islamic studies', 'ISS': 'islamic studies',
    'BUS STUDIES': 'business studies', 'BUS': 'business studies', 'BS': 'business studies',
    'AGRIC': 'agricultural science', 'AGRIC SCI': 'agricultural science',
    'HOME ECONS': 'home economics', 'HOME ECON': 'home economics', 'HE': 'home economics',
    'PHE': 'physical and health education', 'PE': 'physical and health education',
    'COMPUTER': 'computer studies', 'COMP': 'computer studies', 'ICT': 'computer studies',
    'FRE': 'french', 'YOR': 'yoruba', 'IGB': 'igbo', 'HAU': 'hausa', 'ARB': 'arabic',
    'HIST': 'history', 'SEC ED': 'security education',
    'QR': 'quantitative reasoning', 'QUANT': 'quantitative reasoning',
    'VR': 'verbal reasoning', 'VERBAL': 'verbal reasoning',
    'GP': 'general paper', 'GEN PAPER': 'general paper',
}
_STOP = {'AND', '&', 'OF', 'IN', 'THE'}


def _words(s):
    return [w for w in re.sub(r'[^A-Za-z0-9 ]+', ' ', (s or '').upper()).split() if w]


def make_subject_resolver(subjects):
    """Resolve a typed subject against an exam's configured subject list:
    exact → alias → initials (BST, CCA, CRS) → word-prefix (Eng, Basic Sci).
    Returns None when nothing (or more than one subject) matches."""
    by_norm = {' '.join(_words(s)): s for s in subjects}

    def initials(s):
        return ''.join(w[0] for w in _words(s) if w not in _STOP)

    def resolve(raw):
        w = _words(raw)
        if not w:
            return None
        key = ' '.join(w)
        if key in by_norm:
            return by_norm[key]
        target = _SCHOOL_ALIASES.get(key)
        if target:
            tw = _words(target)
            for s in subjects:            # alias → the configured spelling
                sw = _words(s)
                if sw == tw or (len(tw) == 1 and sw and sw[0] == tw[0]):
                    return s
        cands = [s for s in subjects if len(key) >= 2 and ' ' not in key and initials(s) == key]
        if len(cands) == 1:
            return cands[0]
        cands = []
        for s in subjects:
            sw = [x for x in _words(s) if x not in _STOP]
            iw = [x for x in w if x not in _STOP]
            if iw and len(iw) <= len(sw) and all(sw[i].startswith(iw[i]) for i in range(len(iw))):
                cands.append(s)
        if len(cands) == 1:
            return cands[0]
        if len(cands) > 1:                # prefer the one whose word count matches
            exact = [s for s in cands if len([x for x in _words(s) if x not in _STOP]) == len(w)]
            if len(exact) == 1:
                return exact[0]
        return None

    return resolve


def school_exam_spec(scheme, label):
    letters = ', '.join(scheme.grades)

    def parse_value(v):
        raw = (v or '').strip()
        g = raw.upper()
        if _NUM.match(g):
            score = float(g)
            if score > scheme.max_score:
                return None, None, f'score {raw} is above the maximum ({scheme.max_score:g}).'
            return score, scheme.grade_from_score(score), None
        if scheme.band_for_grade(g):
            return None, g, None
        if re.match(r'^[A-F][1-9]$', g):
            return None, None, (f'"{raw}" is a WAEC-style grade — {scheme.exam_name} uses '
                                f'plain letters ({letters}).')
        return None, None, f'"{raw}" is not a {scheme.exam_name} grade (use {letters} or a score).'

    return {'label': label, 'resolve_subject': make_subject_resolver(scheme.subjects),
            'parse_value': parse_value}
