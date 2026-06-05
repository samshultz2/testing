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
# A clean, unambiguous grade (used first so correct text never gets mangled).
_STRICT_GRADE_RE = re.compile(r'\b([A-F][1-9])\b')
# A grade-like token allowing characters Tesseract confuses with a digit
# (l/I/| -> 1, o -> 0, s -> 5). Only used as a fallback when no strict grade is
# found on the line, so clean PDF text is never affected.
_GRADE_TOKEN_RE = re.compile(r'\b([A-Fa-f])\s?([0-9OoIl|Ss])\b')
_DIGIT_FIX = {'l': '1', 'i': '1', '|': '1', 'o': '0', 's': '5'}


def _normalize_grade(letter, second):
    """Turn an OCR'd grade-like token into a valid WAEC grade, or None."""
    if not second.isdigit():
        second = _DIGIT_FIX.get(second.lower(), second)
    grade = f"{letter.upper()}{second}"
    return grade if grade in _GRADE_SET else None


def _grades_in(line):
    """
    Valid WAEC grades found in a line as (position, grade), preferring exact
    matches and only falling back to OCR-confusion matching when none exist.
    """
    strict = [(m.start(), m.group(1)) for m in _STRICT_GRADE_RE.finditer(line)
              if m.group(1) in _GRADE_SET]
    if strict:
        return strict
    lenient = []
    for m in _GRADE_TOKEN_RE.finditer(line):
        g = _normalize_grade(m.group(1), m.group(2))
        if g:
            lenient.append((m.start(), g))
    return lenient

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


def pdf_available():
    """True if PyMuPDF is installed (needed to read PDF results)."""
    try:
        import fitz  # noqa: F401
        return True
    except Exception:
        return False


def extract_text_from_pdf(pdf_bytes):
    """
    Read text from a result PDF. Uses the embedded text layer when present
    (digital PDFs); falls back to rendering each page and OCR'ing it for
    scanned/image-only PDFs.
    """
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype='pdf')
    try:
        parts = [page.get_text().strip() for page in doc]
        combined = '\n'.join(p for p in parts if p).strip()

        # Sparse/empty text layer -> the PDF is almost certainly scanned images.
        if len(combined) < 40 and tesseract_available():
            ocr_parts = []
            for page in doc:
                pix = page.get_pixmap(dpi=200)
                ocr_parts.append(extract_text(pix.tobytes('png')))
            combined = '\n'.join(ocr_parts).strip()
        return combined
    finally:
        doc.close()


def pdf_first_page_png(pdf_bytes):
    """Render the first PDF page to PNG bytes (used as a review preview)."""
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype='pdf')
    try:
        pix = doc[0].get_pixmap(dpi=150)
        return pix.tobytes('png')
    finally:
        doc.close()


def _match_subject(text):
    """Fuzzy-match a fragment of OCR text to a known WAEC subject name."""
    cleaned = re.sub(r'[^A-Za-z ]', ' ', text).strip().lower()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    # Too short to be a subject (e.g. a stray "b" left from a "B3" grade).
    if len(cleaned) < 3:
        return None

    # 1) the full subject name appears in the line text
    for low, original in _SUBJECTS_LOWER.items():
        if low in cleaned:
            return original

    # 2) a reasonably long fragment / fuzzy match (guarded by length so short
    #    noise like a grade token can never masquerade as a subject)
    if len(cleaned) >= 4:
        for low, original in _SUBJECTS_LOWER.items():
            if cleaned in low:
                return original
        close = difflib.get_close_matches(cleaned, list(_SUBJECTS_LOWER.keys()), n=1, cutoff=0.7)
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
    # not a header and not a subject name).
    for line in lines:
        low = line.lower()
        if any(s in low for s in skip):
            continue
        if _match_subject(line) or _grades_in(line):
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

    Handles the common WAEC layouts: subject and grade on the same line, and
    subject/grade split across separate lines or columns.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Classify each line: which known subject (if any) and which grade (if any).
    classified = []
    for line in lines:
        grades = _grades_in(line)
        grade = grades[-1][1] if grades else None       # right-most = grade column
        before = line[:grades[-1][0]] if grades else line
        subject = _match_subject(before) or _match_subject(line)
        classified.append({'subject': subject, 'grade': grade, 'line': line})

    results = []
    seen = set()
    pending_subjects = []   # subject lines still missing a grade (in order)
    pending_grades = []     # grade lines still missing a subject (in order)

    def add(subject, grade, raw):
        if subject and grade and subject not in seen:
            seen.add(subject)
            results.append({'subject': subject, 'grade': grade, 'raw': raw})

    # Pass 1 — same-line pairs; stash the leftovers.
    for c in classified:
        if c['subject'] and c['grade']:
            add(c['subject'], c['grade'], c['line'])
        elif c['subject']:
            pending_subjects.append(c)
        elif c['grade']:
            pending_grades.append(c)

    # Pass 2 — pair leftover subjects with leftover grades in document order
    # (covers column layouts and grade-on-the-next-line layouts).
    for subj_c, grade_c in zip(pending_subjects, pending_grades):
        add(subj_c['subject'], grade_c['grade'], f"{subj_c['line']} | {grade_c['line']}")

    return {
        'name': _extract_name(lines),
        'year': _extract_year(text),
        'subjects': results,
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
