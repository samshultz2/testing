"""
Offline OCR for WAEC result slips (Tesseract).

Given an uploaded result image this module extracts the candidate's name and a
list of {subject, grade} pairs. OCR is never perfect, so the result is always
shown to the user for review/correction before anything is saved.
"""
import io
import os
import re
import difflib

from utils.helpers import WAEC_SUBJECTS, WAEC_GRADES

# Auto-orientation (OSD) is a second Tesseract pass — roughly 40% of a scan's
# time. It only helps sideways/upside-down photos; if you always upload upright
# images or screenshots, set WAEC_OCR_AUTO_ORIENT=0 to skip it and (almost) halve
# scan time on a slow CPU.
_AUTO_ORIENT = os.environ.get('WAEC_OCR_AUTO_ORIENT', '1').strip().lower() not in ('0', 'false', 'no')

# Resource limits for OCR on untrusted uploads (DoS hardening).
_MAX_IMAGE_PIXELS = 50_000_000       # ~50 MP — reject decompression bombs
_OCR_TIMEOUT_SECONDS = 60            # per Tesseract pass (generous for slow CPUs)
_MAX_PDF_OCR_PAGES = 25              # cap pages rendered+OCR'd from a scanned PDF
# Tesseract cost grows ~quadratically with pixels, so a full-resolution phone
# photo (often 12-20 MP) can blow the time budget on a slow CPU. Shrinking the
# longest edge to this before OCR is the single biggest speed-up and does not
# change the recognition engine. Tiny images are still upscaled (below).
_MAX_OCR_DIM = 1800
# Orientation detection (OSD) is a separate full Tesseract pass and is often the
# bigger cost — it doesn't need full resolution, so run it on a small thumbnail.
_OSD_MAX_DIM = 800
# Only upscale genuinely small images (tiny photos benefit); an image already at
# least this wide is left at native size so we don't OCR more pixels than needed.
_MIN_OCR_DIM = 1300

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


def _auto_orient(img, pytesseract):
    """Use Tesseract OSD to fix a sideways/upside-down photo (best effort).

    OSD runs on a small thumbnail — orientation doesn't need full resolution and
    a full-size OSD pass is often the single biggest cost of a scan."""
    try:
        probe = img
        if max(img.size) > _OSD_MAX_DIM:
            s = _OSD_MAX_DIM / max(img.size)
            probe = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))))
        osd = pytesseract.image_to_osd(probe)
        m = re.search(r'Rotate:\s*(\d+)', osd)
        if m:
            angle = int(m.group(1))
            if angle:
                # OSD reports the rotation needed to make text upright.
                img = img.rotate(-angle, expand=True)
    except Exception:
        pass
    return img


def extract_text(image_bytes):
    """Run Tesseract over the image bytes and return the raw text."""
    import pytesseract
    from PIL import Image, ImageOps

    # Decompression-bomb / resource-exhaustion guard: cap how big an image we
    # will decode and OCR (a small file can expand to billions of pixels).
    Image.MAX_IMAGE_PIXELS = _MAX_IMAGE_PIXELS
    img = Image.open(io.BytesIO(image_bytes))
    if img.width * img.height > _MAX_IMAGE_PIXELS:
        raise ValueError('Image is too large to process.')
    # Preprocess: orient via EXIF + OSD, grayscale, autocontrast and upscale a
    # little — this noticeably improves OCR on photographed slips.
    img = ImageOps.exif_transpose(img)
    # Downscale a large photo BEFORE orientation + OCR so a big phone photo can't
    # exceed the Tesseract time budget (this is the fix for "process timeout").
    if max(img.size) > _MAX_OCR_DIM:
        scale = _MAX_OCR_DIM / max(img.size)
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))))
    if _AUTO_ORIENT:
        img = _auto_orient(img, pytesseract)
    img = ImageOps.grayscale(img)
    img = ImageOps.autocontrast(img)
    if max(img.size) < _MIN_OCR_DIM:
        scale = _MIN_OCR_DIM / max(img.size)
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    # Bound a single OCR pass so a crafted image can't hang a worker.
    return pytesseract.image_to_string(img, timeout=_OCR_TIMEOUT_SECONDS)


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
            # Cap the number of rendered+OCR'd pages so a huge PDF can't pin a
            # worker for minutes.
            for i in range(min(doc.page_count, _MAX_PDF_OCR_PAGES)):
                pix = doc[i].get_pixmap(dpi=200)
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


def _expand_inline(lines):
    """Split comma/semicolon separated fragments into their own lines so inline
    SMS-style results ("ENG C6, MAT B3, BIO A1") parse like a table."""
    out = []
    for line in lines:
        for part in re.split(r'[;,]', line):
            part = part.strip(' -\t')
            if part:
                out.append(part)
    return out


def _match_subject_or_code(text):
    """Match a subject by name, then by a short abbreviation code."""
    subject = _match_subject(text)
    if subject:
        return subject
    for token in re.findall(r'\b([A-Za-z]{2,12})\b', text):
        key = token.upper()
        if key in _JAMB_CODES:
            return _JAMB_CODES[key]
    return None


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

    # Classify each fragment: which known subject (if any) and grade (if any).
    # Inline "ENG C6, MAT B3" fragments are split out first.
    classified = []
    for line in _expand_inline(lines):
        grades = _grades_in(line)
        grade = grades[-1][1] if grades else None       # right-most = grade column
        before = line[:grades[-1][0]] if grades else line
        subject = _match_subject_or_code(before) or _match_subject_or_code(line)
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


def _vision_config():
    """Resolve the vision-OCR config from the Settings page (DB) first, then env /
    Config. Never returns the raw key to callers that only need status — it does
    include ``key`` for the extractor, plus a masked form and presence flags for
    the settings UI."""
    import os
    from config import Config
    enabled = bool(getattr(Config, 'OCR_VISION_FALLBACK', False))
    model = getattr(Config, 'OCR_VISION_MODEL', 'claude-haiku-4-5')
    key = os.environ.get('ANTHROPIC_API_KEY', '') or ''
    env_key = bool(key)
    key_source = 'env' if key else None
    try:                                  # DB settings override env/Config when present
        from models import SchoolSettings
        from utils.crypto import decrypt
        ev = SchoolSettings.get('ocr_vision_enabled', None)
        if ev is not None:
            enabled = bool(ev)
        mv = (SchoolSettings.get('ocr_vision_model', '') or '').strip()
        if mv:
            model = mv
        kv = (SchoolSettings.get('ocr_vision_api_key', '') or '').strip()
        if kv:
            dec = decrypt(kv)
            if dec:
                key, key_source = dec, 'settings'
    except Exception:
        pass
    try:
        import anthropic  # noqa: F401
        installed = True
    except Exception:
        installed = False
    masked = ''
    if key:
        masked = (key[:7] + '…' + key[-4:]) if len(key) > 14 else '••••••'
    return {'enabled': enabled, 'model': model, 'key': key, 'has_key': bool(key),
            'key_masked': masked, 'env_key': env_key, 'key_source': key_source,
            'installed': installed}


def vision_available():
    """True if the optional Claude-vision OCR is enabled, has a key, and the
    ``anthropic`` package is importable."""
    cfg = _vision_config()
    return bool(cfg['enabled'] and cfg['has_key'] and cfg['installed'])


def vision_extract(image_bytes, exam='waec', media_type='image/png'):
    """
    Use Claude vision to read a result image into structured data. Returns the
    same dict shape as parse_waec_result / parse_jamb_result, or None on any
    failure (so callers can fall back to Tesseract).
    """
    cfg = _vision_config()
    if not (cfg['enabled'] and cfg['has_key'] and cfg['installed']):
        return None
    try:
        import base64
        import json
        import anthropic

        client = anthropic.Anthropic(api_key=cfg['key'])
        data = base64.standard_b64encode(image_bytes).decode('utf-8')

        if exam == 'jamb':
            instruction = (
                "This is a Nigerian JAMB/UTME result (slip or SMS text). Extract the "
                "candidate name, exam year, total/aggregate score (0-400), and each "
                "subject with its score over 100. Map abbreviations (ENG->English "
                "Language, MAT->Mathematics, PHY->Physics, CHE->Chemistry, etc.). "
                'Return ONLY JSON: {"name": str, "year": int|null, "total_score": '
                'int|null, "subjects": [{"subject": str, "score": int}]}.'
            )
        else:
            instruction = (
                "This is a Nigerian WAEC/SSCE result. Extract the candidate name, "
                "exam year, and each subject with its grade (A1,B2,B3,C4,C5,C6,D7,"
                "E8,F9). Use full subject names. "
                'Return ONLY JSON: {"name": str, "year": int|null, "subjects": '
                '[{"subject": str, "grade": str}]}.'
            )

        message = client.messages.create(
            model=cfg['model'],
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                    {"type": "text", "text": instruction},
                ],
            }],
        )
        text = next((b.text for b in message.content if b.type == "text"), "")
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text[text.find("{"):text.rfind("}") + 1]
        parsed = json.loads(text)

        # Normalise into our standard shape.
        if exam == 'jamb':
            subjects = [{'subject': s.get('subject'), 'score': s.get('score'), 'raw': ''}
                        for s in parsed.get('subjects', []) if s.get('subject')][:4]
            total = parsed.get('total_score')
            if total is None and subjects:
                total = sum(s['score'] for s in subjects if isinstance(s.get('score'), int))
            return {'name': parsed.get('name') or '', 'year': parsed.get('year'),
                    'total_score': total, 'subjects': subjects}
        else:
            subjects = [{'subject': s.get('subject'), 'grade': s.get('grade'), 'raw': ''}
                        for s in parsed.get('subjects', []) if s.get('subject') and s.get('grade')]
            return {'name': parsed.get('name') or '', 'year': parsed.get('year'),
                    'subjects': subjects}
    except Exception:
        return None


# Tokens a cell can hold that mean "no score".
_SHEET_BLANKS = {'', '-', '--', '–', 'nil', 'absent', 'a', 'x', 'na', 'n/a'}


def vision_extract_scoresheet(image_bytes, column_labels, media_type='image/png'):
    """Read a handwritten class broadsheet image with Claude vision.

    ``column_labels`` is the ordered list of assessment-column names the scores
    map to (e.g. ['1st CA', '2nd CA', 'H.A', '3rd CA', 'P/ME', 'CBT', 'PBT']).
    Returns ``[{'student_num': str, 'name': str, 'cells': [str, ...]}]`` (same
    shape as parse_score_sheet) or None on any failure, so the caller falls back
    to Tesseract. The result is always shown in the review grid before saving."""
    cfg = _vision_config()
    if not (cfg['enabled'] and cfg['has_key'] and cfg['installed']):
        return None
    try:
        import base64
        import json
        import anthropic

        client = anthropic.Anthropic(api_key=cfg['key'])
        data = base64.standard_b64encode(image_bytes).decode('utf-8')
        ncol = len(column_labels)
        # Column labels come from admin-defined assessment names. Sanitise before
        # interpolating into the LLM prompt so a crafted name (newlines / fake
        # instructions) can't steer the model: strip control chars, cap length,
        # and quote each label so it reads as data, not a directive.
        import re as _re
        def _clean_label(s):
            s = _re.sub(r'[^\x20-\x7e]', ' ', str(s))   # printable ASCII, no newlines
            return s.strip()[:40]
        cols = ', '.join('"' + _clean_label(c) + '"' for c in column_labels)
        instruction = (
            "This is a Nigerian school class broadsheet (score sheet). Every row is "
            "one student — read ALL rows top to bottom. For each student give their "
            "printed admission/student number (empty string if none), their full "
            "name, and the handwritten scores in EXACTLY this column order:\n"
            f"{cols}\n"
            "Scores are small numbers; use \"\" for any blank, dash, or absent cell. "
            "Ignore the printed Exam-Total and Grand-Total columns. Do not invent "
            'rows. Return ONLY JSON: {"rows": [{"student_num": str, "name": str, '
            '"scores": [str, ...]}]} with one entry per student.'
        )
        message = client.messages.create(
            model=cfg['model'],
            max_tokens=8000,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                    {"type": "text", "text": instruction},
                ],
            }],
        )
        text = next((b.text for b in message.content if b.type == "text"), "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text[text.find("{"):text.rfind("}") + 1]
        parsed = json.loads(text)

        rows = []
        for r in parsed.get('rows', []):
            name = (r.get('name') or '').strip()
            if not name:
                continue
            cells = []
            for v in (r.get('scores') or [])[:ncol]:
                v = '' if v is None else str(v).strip()
                cells.append('' if v.lower() in _SHEET_BLANKS else v)
            cells += [''] * (ncol - len(cells))            # pad short rows
            rows.append({'student_num': (r.get('student_num') or '').strip(),
                         'name': name, 'cells': cells})
        return rows or None
    except Exception:
        return None


def _name_tokens(*parts):
    """Alphabetic name tokens (length >= 2), lower-cased. Drops punctuation,
    numbers and lone initials so ordering and middle names don't defeat matching."""
    out = set()
    for p in parts:
        for t in re.findall(r'[a-z]+', (p or '').lower()):
            if len(t) >= 2:
                out.add(t)
    return out


MATCH_THRESHOLD = 0.6


def _score_pair(name_l, q, student):
    """Similarity in [0, 1] between a scanned/pasted name and one roster student.

    ``name_l`` is the lower-cased name and ``q`` its ``_name_tokens`` set (computed
    once by the caller so batch matching stays O(names x students) not worse)."""
    full = (student.full_name or '').lower()
    alt = f"{(student.first_name or '').lower()} {(student.surname or '').lower()}".strip()
    # order-sensitive similarity (handles spelling/spacing wobble)
    seq = max(
        difflib.SequenceMatcher(None, name_l, full).ratio(),
        difflib.SequenceMatcher(None, name_l, alt).ratio(),
    )
    # order-independent, subset-aware token similarity
    c = _name_tokens(student.full_name, student.first_name, student.surname,
                     getattr(student, 'middle_name', ''))
    tset = 0.0
    if q and c:
        inter = q & c
        smaller = q if len(q) <= len(c) else c
        if q <= c or c <= q:                       # one name fully contains the other
            tset = 0.97 if len(smaller) >= 2 else 0.55
        elif len(inter) >= 2:                      # e.g. first + surname both shared
            tset = 0.9
        else:
            tset = len(inter) / len(q | c)         # single shared token -> low
        tset = max(tset, difflib.SequenceMatcher(
            None, ' '.join(sorted(q)), ' '.join(sorted(c))).ratio())
    return max(seq, tset)


def match_student(name, students):
    """Auto-match an extracted/pasted name to a student. Returns (student|None, score).

    Robust to the ways real name lists differ from the register: word order
    ("Surname Firstname" vs "Firstname Surname"), an extra/absent middle name, and
    minor spelling/spacing. Matching is token-based so "Ada Obi" still matches
    "Obi Ada Chidinma"; a single shared token is deliberately NOT enough to match,
    to avoid linking the wrong pupil."""
    if not name or not students:
        return None, 0.0
    name_l = name.lower().strip()
    q = _name_tokens(name)
    best, best_score = None, 0.0
    for s in students:
        score = _score_pair(name_l, q, s)
        if score > best_score:
            best_score, best = score, s
    if best_score >= MATCH_THRESHOLD:
        return best, round(best_score, 2)
    return None, round(best_score, 2)


def match_students_unique(names, students):
    """Match a batch of names to a roster so each student is used at most once.

    Independent best-match (``match_student`` per row) silently collapses several
    pasted rows onto the same pupil when the roster is missing some of the pasted
    students — the duplicate then overwrites the first at save time, so only a
    handful of scores survive. This assigns greedily by confidence: the most
    certain (row, student) pairs are locked first, and once a student is taken no
    other row can claim them. Rows that can't win a confident, unclaimed student
    are returned unmatched (to be picked manually) rather than colliding.

    ``names`` is a list of strings; returns a list aligned with it of
    ``(student|None, score)``."""
    n = len(names)
    result = [(None, 0.0)] * n
    if not students or not names:
        return result
    # Score every (row, student) pair once.
    triples = []                                   # (score, row_idx, student)
    for i, nm in enumerate(names):
        if not nm:
            continue
        name_l = nm.lower().strip()
        q = _name_tokens(nm)
        for s in students:
            sc = _score_pair(name_l, q, s)
            if sc >= MATCH_THRESHOLD:
                triples.append((sc, i, s))
    # Lock the most confident pairs first; each row and each student used once.
    triples.sort(key=lambda t: t[0], reverse=True)
    used_rows, used_students = set(), set()
    for sc, i, s in triples:
        if i in used_rows or s.id in used_students:
            continue
        result[i] = (s, round(sc, 2))
        used_rows.add(i)
        used_students.add(s.id)
    return result


# ---------------------------------------------------------------------------
# Class broadsheet / score-sheet parsing
# ---------------------------------------------------------------------------

# Header / footer words that signal a line is NOT a student row.
_SHEET_SKIP_WORDS = {
    'NAME', 'NAMES', 'STUDENT', 'STUDENTS', 'NO', 'SN', 'S/N', 'NUMBER',
    'SUBJECT', 'CLASS', 'ARM', 'TERM', 'SESSION', 'TOTAL', 'GRAND', 'EXAM',
    'CA', 'CBT', 'PBT', 'THEORY', 'OBJECTIVE', 'OBJECTIVES', 'PRACTICAL',
    'MIDTERM', 'HOLIDAY', 'ASSIGNMENT', 'SCORE', 'SCORES', 'POSITION',
    'REMARK', 'REMARKS', 'TEACHER', 'SIGN', 'SIGNATURE', 'GENDER', 'SEX',
    'HEADTEACHER', 'HEADMASTER', 'HEADMISTRESS', 'PRINCIPAL', 'DATE',
    'AVERAGE', 'HIGHEST', 'LOWEST', 'MARK', 'MARKS', 'GRADE', 'ET', 'GT',
}

_NUM_TOKEN_RE = re.compile(r'^\d+(?:\.\d+)?$')


def _is_alpha_token(tok):
    """A token that is part of a name: has letters and no digits."""
    return bool(re.search(r'[A-Za-z]', tok)) and not re.search(r'\d', tok)


def parse_score_sheet(text, num_columns):
    """
    Parse a photographed class broadsheet into one row per student.

    For each non-empty line we isolate the student's name (the longest run of
    alphabetic words), a best-guess student number (the longest purely-numeric
    token appearing *before* the name, e.g. an admission/registration number as
    opposed to a small serial number) and the trailing numeric cells, which the
    caller maps positionally to the subject's assessment columns. Up to
    ``num_columns`` cells are kept; extra trailing cells (the printed Exam-Total
    / Grand-Total columns) are dropped.

    OCR is never perfect, so the result is always shown to the user in an
    editable review grid before anything is saved.

    Returns a list of dicts: ``{'student_num': str|'', 'name': str,
    'cells': [str, ...]}``.
    """
    rows = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        tokens = line.split()

        # Find the longest consecutive run of alphabetic tokens — the name.
        best = None  # (start, end, letter_count)
        i = 0
        while i < len(tokens):
            if _is_alpha_token(tokens[i]):
                j = i
                while j < len(tokens) and _is_alpha_token(tokens[j]):
                    j += 1
                letters = sum(len(t) for t in tokens[i:j])
                if best is None or letters > best[2]:
                    best = (i, j, letters)
                i = j
            else:
                i += 1

        # No real name on this line (blank rule, page number, etc.).
        if not best or best[2] < 3:
            continue

        start, end, _ = best
        name = ' '.join(tokens[start:end]).strip()

        # Skip obvious header/footer lines.
        upper_words = {re.sub(r'[^A-Z]', '', w.upper()) for w in name.split()}
        if upper_words and upper_words <= _SHEET_SKIP_WORDS:
            continue

        leading = tokens[:start]
        trailing = tokens[end:]

        # Student number: the longest numeric token before the name (admission
        # numbers are longer than a 1-2 digit serial). None if there is none.
        leading_nums = [t for t in leading if _NUM_TOKEN_RE.match(t)]
        student_num = ''
        if leading_nums:
            student_num = max(leading_nums, key=len)
            # A lone 1-2 digit leading number is almost certainly a serial, not
            # an admission number — ignore it.
            if len(leading_nums) == 1 and len(student_num) <= 2:
                student_num = ''

        # Score cells: numeric runs in the text after the name.
        cells = re.findall(r'\d+(?:\.\d+)?', ' '.join(trailing))
        cells = cells[:num_columns]

        rows.append({
            'student_num': student_num,
            'name': name,
            'cells': cells,
        })
    return rows


# The left-to-right order assessment columns typically appear on a printed
# Nigerian broadsheet (by AssessmentType short_name). Used to map OCR'd numeric
# cells to the right columns regardless of internal storage order.
SHEET_COLUMN_ORDER = ['CA1', 'CA2', 'CA3', 'HA', 'MID', 'CBT', 'EXAM']
