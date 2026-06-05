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

# Common alternate spellings seen on slips (esp. JAMB) mapped to canonical names.
_ALIASES = {
    'use of english': 'English Language',
    'english': 'English Language',
    'maths': 'Mathematics',
    'further maths': 'Further Mathematics',
    'crs': 'Christian Religious Studies',
    'irs': 'Islamic Religious Studies',
    'lit in english': 'Literature in English',
    'literature': 'Literature in English',
    'govt': 'Government',
}


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
        for alias, original in _ALIASES.items():
            if alias in cleaned:
                return original
        close = difflib.get_close_matches(cleaned, list(_SUBJECTS_LOWER.keys()), n=1, cutoff=0.7)
        if close:
            return _SUBJECTS_LOWER[close[0]]
    return None


def _extract_name(lines):
    """Best-effort extraction of the candidate name from the slip."""
    joined = ' '.join(lines)
    # SMS results greet the candidate: "Dear <Name>,"
    mdear = re.search(r"\bdear\s+([A-Za-z][A-Za-z .'\-]{2,60})", joined, re.I)
    if mdear:
        cand = re.split(r'[,\.]', mdear.group(1))[0].strip()
        if len(cand) >= 3:
            return cand.title()

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


_SCORE_RE = re.compile(r'\b(\d{1,3})\b')
_PURE_NUMBER_RE = re.compile(r'^\d{1,3}$')

# JAMB SMS / abbreviation codes -> canonical subject names.
_JAMB_CODES = {
    'ENG': 'English Language', 'ENGLISH': 'English Language', 'USEOFENGLISH': 'English Language',
    'MAT': 'Mathematics', 'MATH': 'Mathematics', 'MATHS': 'Mathematics', 'MTH': 'Mathematics',
    'PHY': 'Physics', 'PHYS': 'Physics',
    'CHE': 'Chemistry', 'CHEM': 'Chemistry',
    'BIO': 'Biology', 'BIOL': 'Biology',
    'ECO': 'Economics', 'ECON': 'Economics', 'ECONS': 'Economics',
    'GOV': 'Government', 'GOVT': 'Government',
    'LIT': 'Literature in English', 'LITERATURE': 'Literature in English',
    'CRS': 'Christian Religious Studies', 'CRK': 'Christian Religious Studies',
    'IRS': 'Islamic Religious Studies', 'IRK': 'Islamic Religious Studies',
    'COM': 'Commerce', 'COMM': 'Commerce', 'COMMERCE': 'Commerce',
    'GEO': 'Geography', 'GEOG': 'Geography',
    'AGR': 'Agricultural Science', 'AGRIC': 'Agricultural Science',
    'ACC': 'Accounting', 'ACCT': 'Accounting', 'ACCOUNTING': 'Accounting',
    'FMT': 'Further Mathematics', 'FME': 'Further Mathematics', 'FMATHS': 'Further Mathematics',
    'CIV': 'Civic Education', 'CIVIC': 'Civic Education',
    'FRE': 'French', 'FRENCH': 'French',
    'HIS': 'History', 'HIST': 'History',
    'DATA': 'Data Processing', 'DPR': 'Data Processing',
}
_CODE_SCORE_RE = re.compile(r'([A-Za-z]{2,15})\s*[:=]\s*(\d{1,3})\b')


def _parse_jamb_sms(text):
    """
    Parse the JAMB SMS / inline format, e.g.
    "...ENG: 56, MAT: 49, PHY: 55, CHE: 40, Aggregate: 200".
    Returns (subjects, total) or (None, None) if it doesn't look like SMS.
    """
    subjects = []
    seen = set()
    total = None
    for word, num in _CODE_SCORE_RE.findall(text):
        key = re.sub(r'[^A-Za-z]', '', word).upper()
        value = int(num)
        if 'AGGREG' in key or key in ('TOTAL', 'SCORE'):
            if 0 <= value <= 400:
                total = value
        elif key in _JAMB_CODES and 0 <= value <= 100:
            subject = _JAMB_CODES[key]
            if subject not in seen:
                seen.add(subject)
                subjects.append({'subject': subject, 'score': value, 'raw': f'{word}: {num}'})
    if len(subjects) >= 2:
        return subjects, total
    return None, None


def _scores_in(line):
    """Subject-score candidates (0-100) on a line as (position, value)."""
    return [(m.start(), int(m.group(1))) for m in _SCORE_RE.finditer(line)
            if 0 <= int(m.group(1)) <= 100]


def _extract_total(text, lines, subjects):
    """Find the JAMB total score (0-400)."""
    # 1) a line explicitly labelled total/aggregate
    for line in lines:
        low = line.lower()
        if 'total' in low or 'aggregate' in low:
            cand = [int(n) for n in re.findall(r'\d{1,3}', line) if 0 <= int(n) <= 400]
            if cand:
                return max(cand)
    # 2) sum of the extracted subject scores
    if subjects:
        s = sum(r['score'] for r in subjects)
        if 0 < s <= 400:
            return s
    # 3) any standalone 3-digit number in range
    for line in lines:
        for n in re.findall(r'\b(\d{3})\b', line):
            if 101 <= int(n) <= 400:
                return int(n)
    return None


def parse_jamb_result(text):
    """
    Parse OCR text from a JAMB result into:
    {'name', 'year', 'total_score', 'subjects': [{'subject','score','raw'}]}.

    Handles same-line "Subject 75" and split "Subject\\n75" / column layouts.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # JAMB SMS / inline "ENG: 56, MAT: 49 ..." format first.
    sms_subjects, sms_total = _parse_jamb_sms(text)
    if sms_subjects:
        sms_subjects = sms_subjects[:4]
        if sms_total is None:
            s = sum(r['score'] for r in sms_subjects)
            sms_total = s if 0 < s <= 400 else None
        return {
            'name': _extract_name(lines),
            'year': _extract_year(text),
            'total_score': sms_total,
            'subjects': sms_subjects,
        }

    classified = []
    for line in lines:
        scores = _scores_in(line)
        score = scores[-1][1] if scores else None
        before = line[:scores[-1][0]] if scores else line
        subject = _match_subject(before) or _match_subject(line)
        classified.append({
            'subject': subject,
            'score': score,
            'pure_number': bool(_PURE_NUMBER_RE.match(line)),
            'line': line,
        })

    results = []
    seen = set()
    pending_subjects = []
    pending_scores = []

    def add(subject, score, raw):
        if subject and score is not None and subject not in seen:
            seen.add(subject)
            results.append({'subject': subject, 'score': score, 'raw': raw})

    for c in classified:
        if c['subject'] and c['score'] is not None:
            add(c['subject'], c['score'], c['line'])
        elif c['subject']:
            pending_subjects.append(c)
        elif c['score'] is not None and c['pure_number']:
            # only a line that is *just* a number counts as a lone score, so
            # dates / reg numbers / centre codes don't get mis-paired
            pending_scores.append(c)

    for subj_c, score_c in zip(pending_subjects, pending_scores):
        add(subj_c['subject'], score_c['score'], f"{subj_c['line']} | {score_c['line']}")

    results = results[:4]  # JAMB is four subjects
    return {
        'name': _extract_name(lines),
        'year': _extract_year(text),
        'total_score': _extract_total(text, lines, results),
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
