"""
Offline OCR for WAEC result slips (Tesseract).

Given an uploaded result image this module extracts the candidate's name and a
list of {subject, grade} pairs. OCR is never perfect, so the result is always
shown to the user for review/correction before anything is saved.
"""
import io
import re
import difflib

from utils.helpers import WAEC_SUBJECTS, WAEC_GRADES

# Valid WAEC grade tokens.
_GRADE_SET = set(WAEC_GRADES)
# Tokens that look like a grade: a letter A-F followed by a digit OR a character
# Tesseract commonly confuses with a digit (l/I/| -> 1, o -> 0, s -> 5, etc.).
_GRADE_TOKEN_RE = re.compile(r'\b([A-Fa-f])\s?([0-9OoIl|SsZzBbGgTt])\b')
_DIGIT_FIX = {'l': '1', 'i': '1', '|': '1', 'o': '0', 's': '5',
              'z': '2', 'b': '8', 'g': '9', 't': '7'}


def _normalize_grade(letter, second):
    """Turn an OCR'd grade-like token into a valid WAEC grade, or None."""
    if not second.isdigit():
        second = _DIGIT_FIX.get(second.lower(), second)
    grade = f"{letter.upper()}{second}"
    return grade if grade in _GRADE_SET else None


def _grades_in(line):
    """All valid WAEC grades found in a line, with their position."""
    found = []
    for m in _GRADE_TOKEN_RE.finditer(line):
        g = _normalize_grade(m.group(1), m.group(2))
        if g:
            found.append((m.start(), g))
    return found

# Lower-cased subject lookups for fuzzy matching.
_SUBJECTS_LOWER = {s.lower(): s for s in WAEC_SUBJECTS}


def tesseract_available():
    """True if the Tesseract engine and Python bindings are usable."""
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def extract_text(image_bytes):
    """Run Tesseract over the image bytes and return the raw text."""
    import pytesseract
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(image_bytes))
    # Preprocess: orient via EXIF, grayscale, autocontrast and upscale a little
    # — this noticeably improves OCR on photographed slips.
    img = ImageOps.exif_transpose(img)
    img = ImageOps.grayscale(img)
    img = ImageOps.autocontrast(img)
    if max(img.size) < 1600:
        scale = 1600 / max(img.size)
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    return pytesseract.image_to_string(img)


def _match_subject(text):
    """Fuzzy-match a fragment of OCR text to a known WAEC subject name."""
    cleaned = re.sub(r'[^A-Za-z ]', ' ', text).strip().lower()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    if not cleaned:
        return None

    # 1) direct containment (handles trailing/leading noise)
    for low, original in _SUBJECTS_LOWER.items():
        if low in cleaned or cleaned in low:
            return original

    # 2) difflib close match on the whole fragment
    close = difflib.get_close_matches(cleaned, list(_SUBJECTS_LOWER.keys()), n=1, cutoff=0.62)
    if close:
        return _SUBJECTS_LOWER[close[0]]
    return None


def _extract_name(lines):
    """Best-effort extraction of the candidate name from the slip."""
    label_re = re.compile(r'(candidate\s*name|name\s*of\s*candidate|name)\s*[:\-]\s*(.+)', re.I)
    skip = ('west african', 'examination', 'council', 'result', 'statement',
            'waec', 'subject', 'grade', 'candidate no', 'exam', 'year')

    for line in lines:
        m = label_re.search(line)
        if m:
            candidate = m.group(2).strip()
            candidate = re.sub(r'\s{2,}.*$', '', candidate)  # drop trailing columns
            if len(candidate) >= 3:
                return candidate.title()

    # Fallback: first line that looks like a person's name (2+ alpha words,
    # not a header).
    for line in lines:
        low = line.lower()
        if any(s in low for s in skip):
            continue
        words = re.findall(r"[A-Za-z][A-Za-z'\-]+", line)
        if 2 <= len(words) <= 5 and sum(len(w) for w in words) >= 6:
            return ' '.join(words).title()
    return ''


def _extract_year(text):
    m = re.search(r'(20\d{2})', text)
    return int(m.group(1)) if m else None


def parse_waec_result(text):
    """
    Parse OCR text into a structured result:
    {'name': str, 'year': int|None, 'subjects': [{'subject', 'grade', 'raw'}]}.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    subjects = []
    seen = set()
    for line in lines:
        grades = _grades_in(line)
        if not grades:
            continue
        pos, grade = grades[-1]  # last grade token on the line
        # subject text is whatever precedes the grade token
        before = line[:pos]
        subject = _match_subject(before) or _match_subject(line)
        if subject and subject not in seen:
            seen.add(subject)
            subjects.append({'subject': subject, 'grade': grade, 'raw': line})

    return {
        'name': _extract_name(lines),
        'year': _extract_year(text),
        'subjects': subjects,
    }


def match_student(name, students):
    """
    Auto-match the extracted name to a student. Returns (student_or_None, score).
    `students` is a list of Student objects.
    """
    if not name or not students:
        return None, 0.0
    name_l = name.lower().strip()

    best = None
    best_score = 0.0
    for s in students:
        full = (s.full_name or '').lower()
        # also try "first surname" ordering since slips vary
        alt = f"{(s.first_name or '').lower()} {(s.surname or '').lower()}".strip()
        score = max(
            difflib.SequenceMatcher(None, name_l, full).ratio(),
            difflib.SequenceMatcher(None, name_l, alt).ratio(),
        )
        if score > best_score:
            best_score, best = score, s
    # Only treat as a confident match above a threshold.
    if best_score >= 0.6:
        return best, round(best_score, 2)
    return None, round(best_score, 2)
