"""WAEC Result Image/PDF Generator — DATA + COMPONENTS + TEMPLATE + RENDERER.

A deterministic ReportLab renderer that turns a student's *actual* stored WAEC
results into a professional result document. It is architected as four clearly
separated concerns so new designs can be added without touching the generator:

    DATA        build_context(student, year)         -> a plain dict of facts
    COMPONENTS  COMPONENT_GROUPS / resolve_show()     -> what may appear + on/off
    TEMPLATE    TEMPLATES + the _t_* layout builders  -> how it looks (5 designs)
    RENDERER    render_pdf() / render_image()          -> PDF, PNG, JPEG bytes

Changing a template never changes the student's data; toggling a component never
changes the template's layout — the template decides *placement*, the component
selection decides *what is shown*.

Rendering is done with ReportLab (PDF) and PyMuPDF (PDF -> PNG/JPEG), both already
project dependencies, so output is deterministic (same data + template + selection
=> same file) and needs no browser.
"""
from __future__ import annotations

import io
import json

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors

from models import SchoolSettings, WAECResult
from utils.analytics_service import AcademicAnalytics
from utils.school import school_profile, logo_path, document_branding

WAEC_GRADES = ['A1', 'B2', 'B3', 'C4', 'C5', 'C6', 'D7', 'E8', 'F9']
DISTINCTION = {'A1', 'B2', 'B3'}
CREDIT = {'A1', 'B2', 'B3', 'C4', 'C5', 'C6'}
FAIL = {'E8', 'F9'}

DEFAULT_GRADE_DESC = {
    'A1': 'Excellent', 'B2': 'Very Good', 'B3': 'Good', 'C4': 'Credit',
    'C5': 'Credit', 'C6': 'Credit', 'D7': 'Pass', 'E8': 'Pass', 'F9': 'Fail',
}


def grade_descriptions():
    """The A1–F9 → description map (configurable via the ``waec_grade_descriptions``
    school setting, else the WAEC-standard default)."""
    raw = SchoolSettings.get('waec_grade_descriptions')
    if raw:
        try:
            m = raw if isinstance(raw, dict) else json.loads(raw)
            return {g: m.get(g, DEFAULT_GRADE_DESC[g]) for g in WAEC_GRADES}
        except (ValueError, TypeError):
            pass
    return dict(DEFAULT_GRADE_DESC)


# --------------------------------------------------------------------------- #
#  TEMPLATES — five genuinely different layouts (not colour variants).         #
# --------------------------------------------------------------------------- #
TEMPLATES = {
    'prestige':     {'name': 'Prestige Certificate',
                     'desc': 'Ornate art-deco frame, crest, gold ribbon, laurel-framed photo, '
                             'dotted-leader rows with circular gold grade badges and an official seal.',
                     'landscape': False},
    'classic':      {'name': 'Classic Academic',
                     'desc': 'Formal navy-and-gold certificate: double border, centred serif '
                             'masthead and a ruled results table with signature lines.',
                     'landscape': False},
    'editorial':    {'name': 'Modern Editorial',
                     'desc': 'Bold magazine layout: a solid indigo masthead, an overlapping photo, '
                             'an oversized year and a minimal list with colour-coded grade chips.',
                     'landscape': False},
    'premium':      {'name': 'Premium Gold',
                     'desc': 'Landscape luxury certificate with an ornate gold frame, script name, '
                             'multi-column results and a central seal.',
                     'landscape': True},
    'contemporary': {'name': 'Contemporary Report',
                     'desc': 'App-style report: an emerald sidebar with photo and stat tiles beside '
                             'a clean results table with rounded grade pills.',
                     'landscape': False},
    'creative':     {'name': 'Creative Academic',
                     'desc': 'Expressive duo-tone geometry: diagonal colour blocks, a circular photo '
                             'and a bold grid of circular grade badges.',
                     'landscape': False},
    'executive':    {'name': 'Executive Academic — 2026',
                     'desc': 'Premium academic publication: crested serif masthead, an editorial '
                             'WASSCE|year headline, a deep-navy candidate band with an integrated '
                             'photo, a ruled subject/grade ledger with a column rule and crest '
                             'watermark, a stat summary band, and a formal seal + QR authentication row.',
                     'landscape': False},
}
DEFAULT_TEMPLATE = 'prestige'

# Every template is drawn directly on the canvas (pixel-precise, professionally
# designed layouts) — see _CANVAS_DRAW.
_CANVAS_TEMPLATES = set(TEMPLATES)


def list_templates():
    return [{'key': k, **v} for k, v in TEMPLATES.items()]


def is_landscape(key):
    return bool(TEMPLATES.get(key, TEMPLATES[DEFAULT_TEMPLATE])['landscape'])


# --------------------------------------------------------------------------- #
#  COMPONENTS — what can be shown, grouped, with sensible defaults.            #
#  ``avail`` decides whether the component is offered at all (data present).   #
# --------------------------------------------------------------------------- #
def _has(ctx, *path):
    cur = ctx
    for p in path:
        cur = (cur or {}).get(p) if isinstance(cur, dict) else None
    return bool(cur)


COMPONENT_GROUPS = [
    ('School Information', [
        {'key': 'school_name', 'label': 'School name', 'default': True,
         'avail': lambda c: _has(c, 'school', 'name')},
        {'key': 'school_logo', 'label': 'School logo', 'default': True,
         'avail': lambda c: _has(c, 'school', 'logo_path')},
        {'key': 'branch', 'label': 'Branch', 'default': False,
         'avail': lambda c: _has(c, 'branch')},
        {'key': 'school_motto', 'label': 'School motto', 'default': True,
         'avail': lambda c: _has(c, 'school', 'motto')},
        {'key': 'school_address', 'label': 'School address', 'default': False,
         'avail': lambda c: _has(c, 'school', 'address')},
        {'key': 'school_phone', 'label': 'School phone', 'default': False,
         'avail': lambda c: _has(c, 'school', 'phone')},
        {'key': 'school_email', 'label': 'School email', 'default': False,
         'avail': lambda c: _has(c, 'school', 'email')},
        {'key': 'school_website', 'label': 'School website', 'default': False,
         'avail': lambda c: _has(c, 'school', 'website')},
    ]),
    ('Student Information', [
        {'key': 'student_name', 'label': 'Student name', 'default': True,
         'avail': lambda c: True},
        {'key': 'student_photo', 'label': 'Student photograph', 'default': True,
         'avail': lambda c: _has(c, 'student', 'photo_path'),
         'config': {'shape': ['rounded', 'rectangle', 'circle'], 'size': ['small', 'medium', 'large']}},
        {'key': 'admission_no', 'label': 'Admission number', 'default': False,
         'avail': lambda c: _has(c, 'student', 'admission_no')},
        {'key': 'candidate_no', 'label': 'Candidate number', 'default': True,
         'avail': lambda c: _has(c, 'student', 'candidate_no'),
         'config': {'label': 'text'}},
        {'key': 'date_of_birth', 'label': 'Date of birth', 'default': False,
         'avail': lambda c: _has(c, 'student', 'dob')},
        {'key': 'gender', 'label': 'Gender', 'default': False,
         'avail': lambda c: _has(c, 'student', 'gender')},
        {'key': 'student_class', 'label': 'Class', 'default': False,
         'avail': lambda c: _has(c, 'student', 'klass')},
        {'key': 'house', 'label': 'House', 'default': False,
         'avail': lambda c: _has(c, 'student', 'house')},
        {'key': 'student_id', 'label': 'Student ID', 'default': False,
         'avail': lambda c: _has(c, 'student', 'admission_no')},
    ]),
    ('Examination Information', [
        {'key': 'exam_name', 'label': 'Examination name', 'default': True, 'avail': lambda c: True},
        {'key': 'exam_year', 'label': 'Examination year', 'default': True, 'avail': lambda c: True},
        {'key': 'exam_number', 'label': 'Examination number', 'default': False,
         'avail': lambda c: _has(c, 'student', 'exam_number')},
        {'key': 'exam_centre', 'label': 'Examination centre', 'default': False,
         'avail': lambda c: _has(c, 'exam', 'centre')},
    ]),
    ('Result Information', [
        {'key': 'subjects', 'label': 'Subjects', 'default': True, 'avail': lambda c: True},
        {'key': 'grades', 'label': 'Grades', 'default': True, 'avail': lambda c: True},
        {'key': 'grade_desc', 'label': 'Grade descriptions', 'default': True, 'avail': lambda c: True},
        {'key': 'grade_points', 'label': 'Grade points', 'default': False, 'avail': lambda c: True},
        {'key': 'total_subjects', 'label': 'Total subjects', 'default': False, 'avail': lambda c: True},
        {'key': 'credits', 'label': 'Number of credits', 'default': False, 'avail': lambda c: True},
        {'key': 'a1_count', 'label': 'Number of A1 grades', 'default': False, 'avail': lambda c: True},
        {'key': 'average', 'label': 'Average points', 'default': False, 'avail': lambda c: True},
        {'key': 'classification', 'label': 'Overall classification', 'default': False, 'avail': lambda c: True},
    ]),
    ('Official / Authorization', [
        {'key': 'principal_name', 'label': 'Principal name', 'default': True,
         'avail': lambda c: _has(c, 'official', 'principal_name')},
        {'key': 'principal_signature', 'label': 'Principal signature', 'default': True, 'avail': lambda c: True},
        {'key': 'exam_officer', 'label': 'Exam officer signature', 'default': False, 'avail': lambda c: True},
        {'key': 'school_stamp', 'label': 'School stamp / seal', 'default': False,
         'avail': lambda c: True},   # the seal is drawn deterministically — no upload required
        {'key': 'date_issued', 'label': 'Date issued', 'default': True, 'avail': lambda c: True},
        {'key': 'verification_code', 'label': 'Verification code', 'default': False, 'avail': lambda c: True},
        {'key': 'qr_code', 'label': 'QR code', 'default': False, 'avail': lambda c: True},
    ]),
    ('Footer', [
        {'key': 'footer_contact', 'label': 'Contact information', 'default': False,
         'avail': lambda c: _has(c, 'school', 'phone') or _has(c, 'school', 'email')},
        {'key': 'footer_website', 'label': 'Website', 'default': False,
         'avail': lambda c: _has(c, 'school', 'website')},
        {'key': 'footer_disclaimer', 'label': 'Disclaimer', 'default': False, 'avail': lambda c: True},
        {'key': 'footer_custom', 'label': 'Custom footer text', 'default': False,
         'avail': lambda c: True, 'config': {'text': 'text'}},
    ]),
]

# flat key -> spec, and the ordered list of all keys
_ALL_COMPONENTS = {c['key']: c for _, items in COMPONENT_GROUPS for c in items}


# Component presets (what appears) — data is never stored here.
PRESETS = {
    'official': {'label': 'Official Result',
                 'keys': ['school_name', 'school_logo', 'school_motto', 'student_name',
                          'student_photo', 'candidate_no', 'exam_name', 'exam_year',
                          'subjects', 'grades', 'grade_desc', 'total_subjects', 'credits',
                          'principal_name', 'principal_signature', 'school_stamp',
                          'date_issued', 'verification_code', 'qr_code']},
    'parent':   {'label': 'Parent Copy',
                 'keys': ['school_name', 'school_logo', 'student_name', 'exam_name',
                          'exam_year', 'subjects', 'grades', 'grade_desc', 'date_issued']},
    'social':   {'label': 'Social / Promotional',
                 'keys': ['school_name', 'school_logo', 'school_motto', 'student_name',
                          'student_photo', 'exam_name', 'exam_year', 'subjects', 'grades',
                          'a1_count', 'classification']},
    'executive': {'label': 'Executive Academic (Full)',
                  'keys': ['school_name', 'school_logo', 'branch', 'school_motto',
                           'school_address', 'student_name', 'student_photo', 'candidate_no',
                           'exam_name', 'exam_year', 'subjects', 'grades',
                           'total_subjects', 'a1_count', 'credits',
                           'principal_name', 'principal_signature', 'school_stamp',
                           'verification_code', 'qr_code', 'footer_contact', 'footer_website']},
}


def available_components(ctx):
    """The component groups annotated with availability for this student's data."""
    out = []
    for group, items in COMPONENT_GROUPS:
        rows = []
        for c in items:
            rows.append({'key': c['key'], 'label': c['label'],
                         'default': c['default'], 'available': bool(c['avail'](ctx)),
                         'config': c.get('config')})
        out.append((group, rows))
    return out


def default_show(ctx):
    """Default on/off map, honouring availability (unavailable => off)."""
    return {k: (c['default'] and bool(c['avail'](ctx))) for k, c in _ALL_COMPONENTS.items()}


def resolve_show(ctx, requested):
    """Merge a requested selection over availability. A component can never be ON
    when its data is missing (so the renderer never draws a broken element)."""
    show = {}
    for k, c in _ALL_COMPONENTS.items():
        avail = bool(c['avail'](ctx))
        want = bool(requested.get(k, c['default'])) if requested else c['default']
        show[k] = avail and want
    return show


def preset_show(ctx, preset_key):
    keys = set((PRESETS.get(preset_key) or {}).get('keys', []))
    return resolve_show(ctx, {k: (k in keys) for k in _ALL_COMPONENTS})


def missing_warnings(ctx, requested):
    """Human warnings for enabled-but-unavailable data (shown at preview, never
    blocks generation for optional info)."""
    warns = []
    for k, c in _ALL_COMPONENTS.items():
        if requested and requested.get(k) and not c['avail'](ctx):
            warns.append(f'{c["label"]} was requested but is not available for this student.')
    n = len(ctx.get('results') or [])
    if n >= 12:
        warns.append(f'This result has {n} subjects — the layout switches to a compact table.')
    if not ctx.get('results'):
        warns.append('This student has no WAEC results recorded for the selected year.')
    return warns


# --------------------------------------------------------------------------- #
#  DATA — assemble a plain dict of facts from the SMS (never mutated by design) #
# --------------------------------------------------------------------------- #
def _local_path(url):
    """Map a stored /static/... media URL to a filesystem path (for ReportLab).
    Returns None for external URLs or missing files."""
    import os
    from flask import current_app
    if not url:
        return None
    u = url.split('?', 1)[0]
    marker = '/static/'
    if marker in u:
        rel = u.split(marker, 1)[1]
        p = os.path.join(current_app.root_path, 'static', rel)
        return p if os.path.exists(p) else None
    return None


def available_years(student):
    return [y[0] for y in (WAECResult.query
            .with_entities(WAECResult.exam_year)
            .filter_by(student_id=student.id)
            .distinct().order_by(WAECResult.exam_year.desc()).all())]


def build_context(student, year):
    """Assemble the immutable DATA context for one student + exam year."""
    g = SchoolSettings.get
    prof = school_profile()
    brand = document_branding()
    desc = grade_descriptions()

    rows = (WAECResult.query.filter_by(student_id=student.id, exam_year=year)
            .order_by(WAECResult.subject).all())
    results = [{'subject': r.subject, 'grade': r.grade,
                'desc': desc.get(r.grade, ''),
                'points': AcademicAnalytics.GRADE_AVERAGE_POINTS.get(r.grade, 0)}
               for r in rows]
    grades = [r.grade for r in rows]
    total = len(grades)
    credits = sum(1 for x in grades if x in CREDIT)
    distinctions = sum(1 for x in grades if x in DISTINCTION)
    a1 = grades.count('A1')
    fails = sum(1 for x in grades if x in FAIL)
    avg = round(sum(AcademicAnalytics.GRADE_AVERAGE_POINTS.get(x, 0) for x in grades) / total, 2) if total else 0
    if credits >= 5:
        classification = 'Distinction' if distinctions >= 5 else 'Credit'
    elif credits >= 1 or (total - fails) >= 1:
        classification = 'Pass'
    else:
        classification = 'Fail'

    branch = None
    try:
        if getattr(student, 'branch', None) is not None:
            branch = student.branch.name
    except Exception:
        branch = None

    # Passport photos live as a BLOB in the tenant DB (StudentPhoto), served via
    # a login-gated route — not a static file. Load the bytes straight from the DB
    # as a ReportLab ImageReader (drawImage accepts it), falling back to a legacy
    # /static/ photo_url if one was ever set that way.
    photo = None
    try:
        from utils import student_photo
        photo = student_photo.photo_reader(student)
    except Exception:
        photo = None
    if photo is None:
        photo = _local_path(getattr(student, 'photo_url', None))
    klass = getattr(student, 'stream', None) or getattr(student, 'current_class', None)

    return {
        'school': {
            'name': prof.get('name'), 'motto': prof.get('motto'),
            'address': prof.get('address'), 'phone': prof.get('phone'),
            'email': prof.get('email'), 'website': g('school_website', '') or '',
            'logo_path': logo_path(),
        },
        'branch': branch,
        'brand': {'primary': brand.get('primary_color') or '#0d6a4e',
                  'accent': brand.get('accent_color') or '#11998e',
                  'secondary': brand.get('secondary_color') or '#334155'},
        'student': {
            'name': student.full_name, 'photo_path': photo,
            'admission_no': getattr(student, 'student_id', None),
            'candidate_no': getattr(student, 'waec_reg_number', None) or getattr(student, 'waec_epin', None),
            'exam_number': getattr(student, 'waec_reg_number', None),
            'dob': (student.date_of_birth.strftime('%d %b %Y') if getattr(student, 'date_of_birth', None) else None),
            'gender': getattr(student, 'gender', None), 'klass': klass,
            'house': getattr(student, 'house', None),
        },
        'exam': {'name': 'West African Senior School Certificate Examination (WAEC)',
                 'short': 'WAEC', 'year': year,
                 'centre': g('waec_exam_centre', '') or ''},
        'results': results,
        'stats': {'total': total, 'credits': credits, 'distinctions': distinctions,
                  'a1': a1, 'fails': fails, 'average': avg, 'classification': classification},
        'official': {'principal_name': g('principal_name', '') or '',
                     'exam_officer_name': g('exam_officer_name', '') or '',
                     'signature_path': _local_path(g('principal_signature_url')),
                     'stamp_path': _local_path(g('school_stamp_url'))},
    }



# --- shared student/exam field pairs (used by all canvas layouts) ---
def _student_pairs(ctx, show):
    st = ctx['student']
    pairs = []
    if show.get('admission_no') and st.get('admission_no'):
        pairs.append(('Admission No.', st['admission_no']))
    if show.get('candidate_no') and st.get('candidate_no'):
        pairs.append(('Candidate No.', st['candidate_no']))
    if show.get('date_of_birth') and st.get('dob'):
        pairs.append(('Date of Birth', st['dob']))
    if show.get('gender') and st.get('gender'):
        pairs.append(('Sex', st['gender']))
    if show.get('student_class') and st.get('klass'):
        pairs.append(('Class', st['klass']))
    if show.get('house') and st.get('house'):
        pairs.append(('House', st['house']))
    if show.get('exam_name'):
        pairs.append(('Examination', ctx['exam']['short']))
    if show.get('exam_year'):
        pairs.append(('Year', str(ctx['exam']['year'])))
    if show.get('exam_centre') and ctx['exam'].get('centre'):
        pairs.append(('Centre', ctx['exam']['centre']))
    return pairs

# --------------------------------------------------------------------------- #
#  CANVAS templates — pixel-precise, ornate designs drawn directly.            #
# --------------------------------------------------------------------------- #
_GOLD = colors.HexColor('#b0892e')
_GOLD_LT = colors.HexColor('#c9a94e')
_GREEN = colors.HexColor('#183a29')
_CREAM = colors.HexColor('#faf7ee')
_INK = colors.HexColor('#1f2937')
_MUTE = colors.HexColor('#6b7280')


def _star(c, cx, cy, r, color):
    """A small 4-point sparkle star."""
    pts = [(cx, cy + r), (cx + r * 0.24, cy + r * 0.24), (cx + r, cy),
           (cx + r * 0.24, cy - r * 0.24), (cx, cy - r), (cx - r * 0.24, cy - r * 0.24),
           (cx - r, cy), (cx - r * 0.24, cy + r * 0.24)]
    p = c.beginPath()
    p.moveTo(*pts[0])
    for x, y in pts[1:]:
        p.lineTo(x, y)
    p.close()
    c.setFillColor(color)
    c.drawPath(p, fill=1, stroke=0)


def _corners(c, W, H, m):
    """Art-deco corners: two solid green wedges + two gold brackets, with stars."""
    s = 78
    # top-right green wedge
    c.setFillColor(_GREEN)
    p = c.beginPath(); p.moveTo(W - m, H - m); p.lineTo(W - m - s, H - m); p.lineTo(W - m, H - m - s); p.close()
    c.drawPath(p, fill=1, stroke=0)
    # bottom-left green wedge
    p = c.beginPath(); p.moveTo(m, m); p.lineTo(m + s, m); p.lineTo(m, m + s); p.close()
    c.drawPath(p, fill=1, stroke=0)
    _star(c, W - m - 20, H - m - 20, 5, _GOLD_LT)
    _star(c, m + 20, m + 20, 5, _GOLD_LT)
    # top-left & bottom-right gold brackets
    c.setStrokeColor(_GOLD); c.setLineWidth(1.4)
    c.line(m, H - m, m + 54, H - m); c.line(m, H - m, m, H - m - 54)
    c.line(W - m, m, W - m - 54, m); c.line(W - m, m, W - m, m + 54)
    _star(c, m + 12, H - m - 12, 4, _GOLD)
    _star(c, W - m - 12, m + 12, 4, _GOLD)


def _ribbon(c, cx, y, text, w=250, h=20):
    """A centred gold banner with notched ends."""
    x = cx - w / 2
    c.setFillColor(_GOLD)
    p = c.beginPath()
    p.moveTo(x, y); p.lineTo(x + w, y); p.lineTo(x + w - 8, y + h / 2); p.lineTo(x + w, y + h)
    p.lineTo(x, y + h); p.lineTo(x + 8, y + h / 2); p.close()
    c.drawPath(p, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont('Helvetica-Bold', 10)
    c.drawCentredString(cx, y + h / 2 - 3.5, text.upper())


def _badge(c, cx, cy, r, grade):
    """A circular gold grade badge with a subtle ring."""
    c.setFillColor(_GOLD)
    c.circle(cx, cy, r, stroke=0, fill=1)
    c.setStrokeColor(_GOLD_LT); c.setLineWidth(1.2)
    c.circle(cx, cy, r - 1.5, stroke=1, fill=0)
    c.setFillColor(colors.white); c.setFont('Times-Bold', 12.5)
    c.drawCentredString(cx, cy - 4.5, grade)


def _rounded_photo(c, path, x, y, w, h, r=8):
    try:
        c.saveState()
        p = c.beginPath(); p.roundRect(x, y, w, h, r); c.clipPath(p, stroke=0, fill=0)
        c.drawImage(path, x, y, w, h, preserveAspectRatio=True, anchor='c', mask='auto')
        c.restoreState()
    except Exception:
        c.restoreState()
    c.setStrokeColor(_GOLD); c.setLineWidth(1.6)
    c.roundRect(x, y, w, h, r, stroke=1, fill=0)


def _faded(path, alpha=0.06):
    """A faint RGBA copy of an image for use as a watermark."""
    try:
        from PIL import Image as PILImage
        im = PILImage.open(path).convert('RGBA')
        a = im.split()[3].point(lambda p: int(p * alpha))
        im.putalpha(a)
        buf = io.BytesIO(); im.save(buf, format='PNG'); buf.seek(0)
        from reportlab.lib.utils import ImageReader
        return ImageReader(buf)
    except Exception:
        return None


def _seal(c, cx, cy, r, name):
    """A drawn official seal: concentric gold rings, centred initials and two
    small star accents (no micro-text, so nothing overlaps at small sizes)."""
    c.setStrokeColor(_GOLD); c.setLineWidth(1.4); c.circle(cx, cy, r, stroke=1, fill=0)
    c.setLineWidth(0.6); c.circle(cx, cy, r - 4, stroke=1, fill=0)
    c.setDash(1, 2); c.circle(cx, cy, r - 7.5, stroke=1, fill=0); c.setDash()
    initials = ''.join(w[0] for w in (name or 'S').split()[:3]).upper() or 'S'
    fs = max(9, min(15, int(r * 0.5)))
    c.setFillColor(_GOLD); c.setFont('Times-Bold', fs)
    c.drawCentredString(cx, cy - fs * 0.36, initials)
    _star(c, cx - r + 6, cy, 2, _GOLD_LT)
    _star(c, cx + r - 6, cy, 2, _GOLD_LT)


def _wrap(c, text, font, size, max_w):
    """Greedy word-wrap → list of lines that fit max_w at (font,size)."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    words, lines, cur = text.split(), [], ''
    for w in words:
        t = (cur + ' ' + w).strip()
        if stringWidth(t, font, size) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def _draw_prestige(c, ctx, show, cfg, verify_url):
    """The ornate portrait result card (matches the reference design)."""
    import datetime
    W, H = A4
    m = 20
    # background + double frame
    c.setFillColor(_CREAM); c.rect(0, 0, W, H, fill=1, stroke=0)
    _corners(c, W, H, m)
    c.setStrokeColor(_GOLD); c.setLineWidth(1.4); c.rect(m + 8, m + 8, W - 2 * (m + 8), H - 2 * (m + 8))
    c.setLineWidth(0.5); c.rect(m + 12, m + 12, W - 2 * (m + 12), H - 2 * (m + 12))

    cx = W / 2
    y = H - m - 40
    # crest / logo
    if show.get('school_logo') and ctx['school'].get('logo_path'):
        try:
            c.drawImage(ctx['school']['logo_path'], cx - 34, y - 40, 68, 68,
                        preserveAspectRatio=True, anchor='c', mask='auto')
        except Exception:
            pass
        y -= 52
    # school name
    if show.get('school_name') and ctx['school'].get('name'):
        c.setFillColor(_GREEN); c.setFont('Times-Bold', 25)
        c.drawCentredString(cx, y, (ctx['school']['name'] or '').upper()); y -= 18
    if show.get('branch') and ctx.get('branch'):
        c.setFillColor(_MUTE); c.setFont('Times-Bold', 11)
        c.drawCentredString(cx, y, ctx['branch'].upper()); y -= 16
    else:
        y -= 4
    # ribbon
    _ribbon(c, cx, y - 6, 'Official Student Result Card', w=250, h=20); y -= 26
    if show.get('exam_name'):
        c.setFillColor(_INK); c.setFont('Helvetica', 8.5)
        c.drawCentredString(cx, y, ctx['exam']['name']); y -= 13
    if show.get('exam_year'):
        c.setFillColor(_INK); c.setFont('Helvetica-Bold', 11)
        c.drawCentredString(cx, y, f"YEAR: {ctx['exam']['year']}"); y -= 8

    # ---- identity row (photo + name/ids) ----
    y -= 18
    left = m + 40
    photo_w, photo_h = 96, 116
    text_x = left
    if show.get('student_photo') and ctx['student'].get('photo_path'):
        _rounded_photo(c, ctx['student']['photo_path'], left, y - photo_h, photo_w, photo_h)
        _star(c, left + photo_w / 2, y - photo_h - 8, 4, _GOLD)
        text_x = left + photo_w + 20
    top = y
    c.setFillColor(_MUTE); c.setFont('Helvetica', 9.5)
    c.drawString(text_x, top - 6, 'Candidate Name:')
    if show.get('student_name'):
        c.setFillColor(_GREEN);
        name = (ctx['student']['name'] or '').upper()
        lines = _wrap(c, name, 'Times-Bold', 24, W - m - 40 - text_x)
        ny = top - 30
        c.setFont('Times-Bold', 24)
        for ln in lines[:2]:
            c.drawString(text_x, ny, ln); ny -= 26
        idy = ny - 2
    else:
        idy = top - 34
    c.setFillColor(_INK); c.setFont('Helvetica', 9.5)
    if show.get('admission_no') and ctx['student'].get('admission_no'):
        c.drawString(text_x, idy, f"Student ID: {ctx['student']['admission_no']}"); idy -= 14
    if show.get('candidate_no') and ctx['student'].get('candidate_no'):
        lbl = (cfg.get('candidate_no') or {}).get('label') or 'Exam Number'
        c.drawString(text_x, idy, f"{lbl}: {ctx['student']['candidate_no']}"); idy -= 14
    y = min(y - photo_h, idy) - 16

    # ---- results panel ----
    if show.get('subjects') and ctx['results']:
        panel_x, panel_r = m + 24, W - m - 24
        panel_top = y
        n = len(ctx['results'])
        row_h = 30 if n <= 9 else (26 if n <= 11 else 22)
        panel_h = row_h * n + 24
        panel_bottom = panel_top - panel_h
        c.setFillColor(colors.HexColor('#f3efe2'))
        c.roundRect(panel_x, panel_bottom, panel_r - panel_x, panel_h, 10, stroke=0, fill=1)
        c.setStrokeColor(_GOLD_LT); c.setLineWidth(1); c.roundRect(panel_x, panel_bottom, panel_r - panel_x, panel_h, 10, stroke=1, fill=0)
        # watermark crest
        wm = _faded(ctx['school'].get('logo_path'), 0.07) if ctx['school'].get('logo_path') else None
        if wm:
            try:
                sz = min(panel_r - panel_x, panel_h) * 0.7
                c.drawImage(wm, cx - sz / 2, panel_bottom + (panel_h - sz) / 2, sz, sz,
                            preserveAspectRatio=True, anchor='c', mask='auto')
            except Exception:
                pass
        show_desc = show.get('grade_desc')
        rx1 = panel_x + 22
        rx2 = panel_r - 26
        fs = 13 if n <= 9 else (11.5 if n <= 11 else 10)
        from reportlab.pdfbase.pdfmetrics import stringWidth
        ry = panel_top - 22
        for r in ctx['results']:
            c.setFillColor(_INK); c.setFont('Helvetica', fs)
            c.drawString(rx1, ry - 4, r['subject'])
            sw = stringWidth(r['subject'], 'Helvetica', fs)
            if show_desc and r.get('desc'):
                c.setFillColor(_MUTE); c.setFont('Helvetica-Oblique', fs - 3.5)
                c.drawString(rx1 + sw + 8, ry - 3.5, f"· {r['desc']}")
            # dotted leader
            if show.get('grades'):
                c.setStrokeColor(colors.HexColor('#9ca3af')); c.setLineWidth(0.8); c.setDash(1, 2.4)
                lead_start = rx1 + sw + (70 if (show_desc and r.get('desc')) else 12)
                c.line(lead_start, ry - 5, rx2 - 24, ry - 5); c.setDash()
                _badge(c, rx2 - 12, ry - 5, 11 if n <= 11 else 9.5, r['grade'])
            ry -= row_h
        y = panel_bottom - 20

    # ---- signatures / seal ----
    seg_top = max(y, m + 120)
    lx = m + 30
    c.setFillColor(_INK); c.setFont('Helvetica-Bold', 9)
    if show.get('principal_signature') or show.get('principal_name'):
        c.drawString(lx, seg_top, 'AUTHORIZED SIGNATURES')
        c.drawString(lx, seg_top - 11, 'AND VERIFICATION.')
        sy = seg_top - 42
        sig = ctx['official'].get('signature_path') if show.get('principal_signature') else None
        if sig:
            try:
                c.drawImage(sig, lx, sy - 4, 90, 26, preserveAspectRatio=True, anchor='sw', mask='auto')
            except Exception:
                sig = None
        if not sig:
            c.setFillColor(_INK); c.setFont('Times-Italic', 18)
            c.drawString(lx, sy, 'Signature')
        c.setStrokeColor(_INK); c.setLineWidth(0.8); c.line(lx, sy - 8, lx + 150, sy - 8)
        if show.get('principal_name') and ctx['official'].get('principal_name'):
            c.setFillColor(_INK); c.setFont('Helvetica-Bold', 10)
            c.drawString(lx, sy - 22, ctx['official']['principal_name'].upper())
        c.setFillColor(_MUTE); c.setFont('Helvetica', 8.5)
        c.drawString(lx, sy - 34, 'Principal')
    # right: seal + certified box
    if show.get('school_stamp') or show.get('date_issued'):
        rx = W - m - 200
        c.setFillColor(_INK); c.setFont('Helvetica-Bold', 9)
        c.drawString(rx, seg_top, 'OFFICIAL SCHOOL SEAL')
        _seal(c, rx + 34, seg_top - 40, 30, ctx['school'].get('name'))
        # certified true copy dashed box
        bx = rx + 92
        c.setStrokeColor(colors.HexColor('#9ca3af')); c.setLineWidth(0.8); c.setDash(2, 2)
        c.roundRect(bx, seg_top - 62, 84, 44, 5, stroke=1, fill=0); c.setDash()
        c.setFillColor(_MUTE); c.setFont('Helvetica-Bold', 7)
        c.drawCentredString(bx + 42, seg_top - 36, 'CERTIFIED')
        c.drawCentredString(bx + 42, seg_top - 46, 'TRUE COPY')
        if show.get('date_issued'):
            c.setFillColor(_INK); c.setFont('Helvetica', 9)
            c.drawString(rx, seg_top - 84, 'Date of issue: ' + datetime.date.today().strftime('%B %d, %Y'))
        if show.get('verification_code') and ctx.get('verify_code'):
            c.setFillColor(_MUTE); c.setFont('Helvetica', 7.5)
            c.drawString(rx, seg_top - 96, 'Verify: ' + ctx['verify_code'])
        if show.get('qr_code') and verify_url:
            qi = _faded(None)  # placeholder guard
            try:
                import qrcode
                from reportlab.lib.utils import ImageReader
                qbuf = io.BytesIO(); qrcode.make(verify_url).save(qbuf, format='PNG'); qbuf.seek(0)
                c.drawImage(ImageReader(qbuf), W - m - 74, m + 30, 44, 44, mask='auto')
            except Exception:
                pass

    # ---- footer ----
    if show.get('footer_contact') or show.get('footer_website') or show.get('school_name'):
        c.setStrokeColor(_GOLD_LT); c.setLineWidth(0.6); c.line(m + 40, m + 44, W - m - 40, m + 44)
        parts = []
        if ctx['school'].get('address'):
            parts.append(ctx['school']['address'])
        c.setFillColor(_INK); c.setFont('Helvetica-Bold', 8.5)
        head = ctx['school'].get('name', '')
        c.drawCentredString(cx, m + 32, head + ('  |  ' + parts[0] if parts else ''))
        contacts = []
        if show.get('footer_website') and ctx['school'].get('website'):
            contacts.append(ctx['school']['website'])
        if show.get('footer_contact'):
            if ctx['school'].get('phone'):
                contacts.append(ctx['school']['phone'])
            if ctx['school'].get('email'):
                contacts.append(ctx['school']['email'])
        if contacts:
            c.setFillColor(_MUTE); c.setFont('Helvetica', 8)
            c.drawCentredString(cx, m + 22, '  |  '.join(contacts))


# ---- shared canvas helpers used by the other five designs -------------------
def _grade_band(g):
    if g in ('A1', 'B2', 'B3'):
        return 'dist'
    if g in ('C4', 'C5', 'C6'):
        return 'credit'
    if g in ('D7', 'E8'):
        return 'pass'
    return 'fail'


def _band_color(g, palette):
    return palette[_grade_band(g)]


def _spaced(c, cx, y, text, font, size, space, color):
    """Centred text with manual letter-spacing (Canvas has no char-space API)."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    c.setFillColor(color); c.setFont(font, size)
    total = sum(stringWidth(ch, font, size) + space for ch in text) - (space if text else 0)
    x = cx - total / 2
    for ch in text:
        c.drawString(x, y, ch); x += stringWidth(ch, font, size) + space


def _divider(c, cx, y, w, color):
    c.setStrokeColor(color); c.setLineWidth(1)
    c.line(cx - w / 2, y, cx - 12, y); c.line(cx + 12, y, cx + w / 2, y)
    c.setFillColor(color)
    p = c.beginPath(); p.moveTo(cx, y + 5); p.lineTo(cx + 6, y); p.lineTo(cx, y - 5); p.lineTo(cx - 6, y); p.close()
    c.drawPath(p, fill=1, stroke=0)


def _pill(c, x, y, w, h, text, fill, tc=colors.white, fs=10):
    c.setFillColor(fill); c.roundRect(x, y, w, h, h / 2.0, stroke=0, fill=1)
    c.setFillColor(tc); c.setFont('Helvetica-Bold', fs)
    c.drawCentredString(x + w / 2, y + h / 2 - fs * 0.35, text)


def _stat_tile(c, x, y, w, h, label, value, bg, labelc, valuec, alpha=None, rad=8):
    if alpha is not None:
        c.saveState(); c.setFillAlpha(alpha)
    c.setFillColor(bg); c.roundRect(x, y, w, h, rad, stroke=0, fill=1)
    if alpha is not None:
        c.restoreState()
    c.setFillColor(valuec); c.setFont('Helvetica-Bold', 17)
    c.drawString(x + 11, y + h - 23, str(value))
    c.setFillColor(labelc); c.setFont('Helvetica-Bold', 7)
    c.drawString(x + 11, y + 8, label.upper())


def _circle_photo(c, path, cx, cy, r, ring, ring_w=3):
    try:
        c.saveState()
        p = c.beginPath(); p.circle(cx, cy, r); c.clipPath(p, stroke=0, fill=0)
        c.drawImage(path, cx - r, cy - r, 2 * r, 2 * r, preserveAspectRatio=True, anchor='c', mask='auto')
        c.restoreState()
    except Exception:
        c.restoreState()
    c.setStrokeColor(ring); c.setLineWidth(ring_w); c.circle(cx, cy, r, stroke=1, fill=0)


def _square_photo(c, path, x, y, w, h, border, bw=4):
    c.setFillColor(border); c.rect(x - bw, y - bw, w + 2 * bw, h + 2 * bw, fill=1, stroke=0)
    try:
        c.drawImage(path, x, y, w, h, preserveAspectRatio=True, anchor='c', mask='auto')
    except Exception:
        c.setFillColor(colors.HexColor('#e5e7eb')); c.rect(x, y, w, h, fill=1, stroke=0)


def _issue_date():
    import datetime
    return datetime.date.today()


# ===========================================================================
#  Design 2 — CLASSIC ACADEMIC (formal navy + gold certificate, portrait)
# ===========================================================================
def _draw_classic(c, ctx, show, cfg, verify_url):
    W, H = A4
    m = 40
    NAVY = colors.HexColor('#16294d'); GOLD = colors.HexColor('#b0892e')
    INK = colors.HexColor('#1f2937'); MUTE = colors.HexColor('#6b7280')
    c.setFillColor(colors.white); c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setStrokeColor(NAVY); c.setLineWidth(3); c.rect(m - 16, m - 16, W - 2 * (m - 16), H - 2 * (m - 16))
    c.setStrokeColor(GOLD); c.setLineWidth(1); c.rect(m - 10, m - 10, W - 2 * (m - 10), H - 2 * (m - 10))
    for dx, dy in [(m - 16, m - 16), (W - (m - 16), m - 16), (m - 16, H - (m - 16)), (W - (m - 16), H - (m - 16))]:
        c.setFillColor(GOLD)
        p = c.beginPath(); p.moveTo(dx, dy + 6); p.lineTo(dx + 6, dy); p.lineTo(dx, dy - 6); p.lineTo(dx - 6, dy); p.close()
        c.drawPath(p, fill=1, stroke=0)
    cx = W / 2; y = H - m - 24
    if show.get('school_logo') and ctx['school'].get('logo_path'):
        try:
            c.drawImage(ctx['school']['logo_path'], cx - 24, y - 40, 48, 48, preserveAspectRatio=True, anchor='c', mask='auto')
        except Exception:
            pass
        y -= 48
    if show.get('school_name') and ctx['school'].get('name'):
        c.setFillColor(NAVY); c.setFont('Times-Bold', 24)
        c.drawCentredString(cx, y, ctx['school']['name'].upper()); y -= 18
    if show.get('branch') and ctx.get('branch'):
        c.setFillColor(MUTE); c.setFont('Times-Italic', 11); c.drawCentredString(cx, y, ctx['branch']); y -= 14
    y -= 4
    _divider(c, cx, y, 200, GOLD); y -= 20
    _spaced(c, cx, y, 'STATEMENT OF EXAMINATION RESULT', 'Helvetica-Bold', 11, 2, NAVY); y -= 16
    if show.get('exam_name'):
        c.setFillColor(INK); c.setFont('Helvetica', 8.5); c.drawCentredString(cx, y, ctx['exam']['name']); y -= 13
    if show.get('exam_year'):
        c.setFillColor(INK); c.setFont('Helvetica-Bold', 11); c.drawCentredString(cx, y, f"YEAR: {ctx['exam']['year']}"); y -= 6
    y -= 16
    if show.get('student_name'):
        for ln in _wrap(c, ctx['student']['name'].upper(), 'Times-Bold', 22, W - 2 * m)[:2]:
            c.setFillColor(INK); c.setFont('Times-Bold', 22); c.drawCentredString(cx, y, ln); y -= 24
    pairs = _student_pairs(ctx, show)
    if pairs:
        c.setFillColor(MUTE); c.setFont('Helvetica', 9.5)
        c.drawCentredString(cx, y, '   •   '.join(f'{l}: {v}' for l, v in pairs)); y -= 14
    y -= 12
    # results table
    if show.get('subjects') and ctx['results']:
        x0, x1 = m + 6, W - m - 6
        has_desc = show.get('grade_desc')
        grade_w = 70; desc_w = 120 if has_desc else 0
        subj_w = (x1 - x0) - grade_w - desc_w
        n = len(ctx['results'])
        hh = 24; rh = 26 if n <= 9 else (23 if n <= 11 else 20)
        c.setFillColor(NAVY); c.rect(x0, y - hh, x1 - x0, hh, fill=1, stroke=0)
        c.setFillColor(colors.white); c.setFont('Helvetica-Bold', 9.5)
        c.drawString(x0 + 12, y - hh + 8, 'SUBJECT')
        c.drawCentredString(x0 + subj_w + grade_w / 2, y - hh + 8, 'GRADE')
        if has_desc:
            c.drawString(x0 + subj_w + grade_w + 12, y - hh + 8, 'REMARK')
        ry = y - hh
        for i, r in enumerate(ctx['results']):
            if i % 2:
                c.setFillColor(colors.HexColor('#f3f5f9')); c.rect(x0, ry - rh, x1 - x0, rh, fill=1, stroke=0)
            c.setFillColor(INK); c.setFont('Helvetica', 10.5 if n <= 11 else 9.5)
            c.drawString(x0 + 12, ry - rh + rh / 2 - 4, r['subject'])
            c.setFillColor(NAVY); c.setFont('Helvetica-Bold', 11 if n <= 11 else 10)
            c.drawCentredString(x0 + subj_w + grade_w / 2, ry - rh + rh / 2 - 4, r['grade'])
            if has_desc:
                c.setFillColor(MUTE); c.setFont('Helvetica', 9)
                c.drawString(x0 + subj_w + grade_w + 12, ry - rh + rh / 2 - 4, r['desc'])
            ry -= rh
        c.setStrokeColor(colors.HexColor('#d7ddea')); c.setLineWidth(0.6); c.rect(x0, ry, x1 - x0, y - hh - ry + hh, fill=0, stroke=1)
        c.line(x0 + subj_w, ry, x0 + subj_w, y - hh)
        if has_desc:
            c.line(x0 + subj_w + grade_w, ry, x0 + subj_w + grade_w, y - hh)
        y = ry - 16
    # summary line
    stbits = []
    st = ctx['stats']
    if show.get('total_subjects'):
        stbits.append(f"Subjects: {st['total']}")
    if show.get('credits'):
        stbits.append(f"Credits: {st['credits']}")
    if show.get('a1_count'):
        stbits.append(f"A1: {st['a1']}")
    if show.get('average'):
        stbits.append(f"Average: {st['average']}")
    if show.get('classification'):
        stbits.append(f"Classification: {st['classification']}")
    if stbits:
        c.setFillColor(NAVY); c.setFont('Helvetica-Bold', 10)
        c.drawCentredString(cx, y, '     '.join(stbits)); y -= 8
    # signatures
    sy = max(m + 96, y - 24)
    sigs = []
    if show.get('principal_signature') or show.get('principal_name'):
        sigs.append((ctx['official'].get('signature_path') if show.get('principal_signature') else None,
                     ctx['official'].get('principal_name') if show.get('principal_name') else '', 'Principal'))
    if show.get('exam_officer'):
        sigs.append((None, ctx['official'].get('exam_officer_name', ''), 'Examination Officer'))
    if sigs:
        span = (W - 2 * m - 40) / len(sigs)
        for i, (sig, name, role) in enumerate(sigs):
            lx = m + 20 + i * span + span / 2
            if sig:
                try:
                    c.drawImage(sig, lx - 45, sy + 2, 90, 24, preserveAspectRatio=True, anchor='s', mask='auto')
                except Exception:
                    pass
            c.setStrokeColor(INK); c.setLineWidth(0.8); c.line(lx - 70, sy, lx + 70, sy)
            if name:
                c.setFillColor(INK); c.setFont('Helvetica-Bold', 10); c.drawCentredString(lx, sy - 13, name.upper())
            c.setFillColor(MUTE); c.setFont('Helvetica', 8.5); c.drawCentredString(lx, sy - 24, role)
    # seal + date
    if show.get('school_stamp'):
        _seal(c, W - m - 44, sy + 6, 26, ctx['school'].get('name'))
    if show.get('date_issued'):
        c.setFillColor(MUTE); c.setFont('Helvetica', 8.5)
        c.drawCentredString(cx, m + 22, 'Issued ' + _issue_date().strftime('%d %B %Y'))


# ===========================================================================
#  Design 3 — MODERN EDITORIAL (bold indigo masthead, portrait)
# ===========================================================================
def _draw_editorial(c, ctx, show, cfg, verify_url):
    W, H = A4
    INDIGO = colors.HexColor('#312e81'); INK = colors.HexColor('#111827'); MUTE = colors.HexColor('#6b7280')
    PAL = {'dist': colors.HexColor('#0d9488'), 'credit': colors.HexColor('#4f46e5'),
           'pass': colors.HexColor('#d97706'), 'fail': colors.HexColor('#dc2626')}
    c.setFillColor(colors.white); c.rect(0, 0, W, H, fill=1, stroke=0)
    hh = 232
    c.setFillColor(INDIGO); c.rect(0, H - hh, W, hh, fill=1, stroke=0)
    # oversized year, faint
    if show.get('exam_year'):
        c.saveState(); c.setFillAlpha(0.16); c.setFillColor(colors.white); c.setFont('Helvetica-Bold', 96)
        c.drawRightString(W - 40, H - 150, str(ctx['exam']['year'])); c.restoreState()
    if show.get('school_logo') and ctx['school'].get('logo_path'):
        try:
            c.drawImage(ctx['school']['logo_path'], W - 92, H - 78, 48, 48, preserveAspectRatio=True, anchor='c', mask='auto')
        except Exception:
            pass
    c.setFillColor(colors.HexColor('#c7d2fe')); c.setFont('Helvetica-Bold', 11)
    c.drawString(48, H - 58, 'WAEC RESULT')
    ny = H - 92
    if show.get('school_name'):
        for ln in _wrap(c, ctx['school']['name'], 'Helvetica-Bold', 30, W - 200)[:2]:
            c.setFillColor(colors.white); c.setFont('Helvetica-Bold', 30); c.drawString(48, ny, ln); ny -= 32
    if show.get('branch') and ctx.get('branch'):
        c.setFillColor(colors.HexColor('#a5b4fc')); c.setFont('Helvetica', 11); c.drawString(48, ny, ctx['branch'])
    # photo overlaps header
    px, py = 48, H - hh - 46
    text_x = 48
    if show.get('student_photo') and ctx['student'].get('photo_path'):
        _square_photo(c, ctx['student']['photo_path'], px, py, 92, 92, colors.white, 4)
        text_x = px + 92 + 20
    nY = H - hh - 6
    c.setFillColor(MUTE); c.setFont('Helvetica', 9); c.drawString(text_x, nY, 'CANDIDATE')
    if show.get('student_name'):
        for ln in _wrap(c, ctx['student']['name'], 'Helvetica-Bold', 21, W - text_x - 40)[:2]:
            c.setFillColor(INK); c.setFont('Helvetica-Bold', 21); c.drawString(text_x, nY - 22, ln); nY -= 22
    iy = nY - 40
    c.setFillColor(MUTE); c.setFont('Helvetica', 9.5)
    idbits = _student_pairs(ctx, show)
    if idbits:
        c.drawString(text_x, nY - 40, '   '.join(f'{l}: {v}' for l, v in idbits[:3]))
    # results list
    y = py - 40
    x0, x1 = 48, W - 48
    n = len(ctx['results'])
    rh = 34 if n <= 9 else (28 if n <= 11 else 24)
    if show.get('subjects'):
        for r in ctx['results']:
            c.setFillColor(INK); c.setFont('Helvetica', 13 if n <= 11 else 11)
            c.drawString(x0, y - 5, r['subject'])
            if show.get('grade_desc') and r.get('desc'):
                sw = _sw(r['subject'], 'Helvetica', 13 if n <= 11 else 11)
                c.setFillColor(MUTE); c.setFont('Helvetica', 9); c.drawString(x0 + sw + 10, y - 5, r['desc'])
            if show.get('grades'):
                _pill(c, x1 - 40, y - 12, 40, 20, r['grade'], _band_color(r['grade'], PAL), fs=11)
            c.setStrokeColor(colors.HexColor('#e5e7eb')); c.setLineWidth(0.8); c.line(x0, y - rh + 8, x1, y - rh + 8)
            y -= rh
    # stat trio
    trio = []
    st = ctx['stats']
    if show.get('credits'):
        trio.append(('CREDITS', st['credits']))
    if show.get('a1_count'):
        trio.append(('A1 GRADES', st['a1']))
    if show.get('average'):
        trio.append(('AVERAGE', st['average']))
    if show.get('classification'):
        trio.append(('CLASS', st['classification']))
    if trio:
        y -= 6
        tw = (x1 - x0) / len(trio)
        for i, (l, v) in enumerate(trio):
            tx = x0 + i * tw
            c.setFillColor(INDIGO); c.setFont('Helvetica-Bold', 26); c.drawString(tx, y - 24, str(v))
            c.setFillColor(MUTE); c.setFont('Helvetica-Bold', 8); c.drawString(tx, y - 38, l)
        y -= 52
    # signature + date footer
    fy = max(64, y - 10)
    if show.get('principal_name') or show.get('principal_signature'):
        sig = ctx['official'].get('signature_path') if show.get('principal_signature') else None
        if sig:
            try:
                c.drawImage(sig, x0, fy + 2, 90, 24, preserveAspectRatio=True, anchor='sw', mask='auto')
            except Exception:
                pass
        c.setStrokeColor(INK); c.setLineWidth(0.8); c.line(x0, fy, x0 + 150, fy)
        c.setFillColor(INK); c.setFont('Helvetica-Bold', 10)
        if show.get('principal_name'):
            c.drawString(x0, fy - 13, (ctx['official'].get('principal_name') or '').upper())
        c.setFillColor(MUTE); c.setFont('Helvetica', 8.5); c.drawString(x0, fy - 24, 'Principal')
    if show.get('date_issued'):
        c.setFillColor(MUTE); c.setFont('Helvetica', 9); c.drawRightString(x1, fy - 4, 'Issued ' + _issue_date().strftime('%d %b %Y'))


# ===========================================================================
#  Design 4 — PREMIUM GOLD (landscape luxury certificate)
# ===========================================================================
def _draw_premium(c, ctx, show, cfg, verify_url):
    W, H = landscape(A4)
    CREAM = colors.HexColor('#fbf8f0'); GOLD = colors.HexColor('#b0892e'); GOLD_LT = colors.HexColor('#c9a94e')
    CHAR = colors.HexColor('#2b2b2b'); MUTE = colors.HexColor('#7c6f57')
    c.setFillColor(CREAM); c.rect(0, 0, W, H, fill=1, stroke=0)
    m = 26
    c.setStrokeColor(GOLD); c.setLineWidth(3); c.rect(m, m, W - 2 * m, H - 2 * m)
    c.setLineWidth(0.8); c.rect(m + 6, m + 6, W - 2 * (m + 6), H - 2 * (m + 6))
    # corner flourishes
    for (ox, oy, sx, sy) in [(m + 6, H - m - 6, 1, -1), (W - m - 6, H - m - 6, -1, -1),
                             (m + 6, m + 6, 1, 1), (W - m - 6, m + 6, -1, 1)]:
        c.setStrokeColor(GOLD_LT); c.setLineWidth(1)
        c.line(ox, oy, ox + sx * 40, oy); c.line(ox, oy, ox, oy + sy * 40)
        _star(c, ox + sx * 12, oy + sy * 12, 4, GOLD)
    cx = W / 2; y = H - m - 46
    if show.get('school_logo') and ctx['school'].get('logo_path'):
        try:
            c.drawImage(ctx['school']['logo_path'], cx - 26, y - 30, 52, 52, preserveAspectRatio=True, anchor='c', mask='auto')
        except Exception:
            pass
        y -= 40
    if show.get('school_name'):
        c.setFillColor(CHAR); c.setFont('Times-Bold', 22); c.drawCentredString(cx, y, ctx['school']['name'].upper()); y -= 20
    _spaced(c, cx, y, 'CERTIFICATE OF EXAMINATION RESULT', 'Helvetica-Bold', 12, 3, GOLD); y -= 16
    _divider(c, cx, y, 260, GOLD); y -= 22
    c.setFillColor(MUTE); c.setFont('Times-Italic', 12); c.drawCentredString(cx, y, 'This is to certify that'); y -= 30
    if show.get('student_name'):
        c.setFillColor(CHAR); c.setFont('Times-BoldItalic', 34); c.drawCentredString(cx, y, ctx['student']['name']); y -= 8
        c.setStrokeColor(GOLD_LT); c.setLineWidth(0.8); c.line(cx - 180, y - 4, cx + 180, y - 4); y -= 20
    line2 = 'sat the ' + (ctx['exam']['short'] if show.get('exam_name') else '') + (f" {ctx['exam']['year']}" if show.get('exam_year') else '') + ' examination with the following results:'
    c.setFillColor(MUTE); c.setFont('Times-Italic', 11); c.drawCentredString(cx, y, line2.strip()); y -= 24
    # multi-column results
    if show.get('subjects') and ctx['results']:
        res = ctx['results']; n = len(res)
        ncol = 1 if n <= 5 else (2 if n <= 12 else 3)
        per = -(-n // ncol)
        area_x0, area_x1 = m + 40, W - m - 40
        col_w = (area_x1 - area_x0) / ncol
        rh = 26 if per <= 6 else 22
        top = y
        for i, r in enumerate(res):
            col = i // per; row = i % per
            bx = area_x0 + col * col_w + 8; by = top - row * rh
            c.setFillColor(CHAR); c.setFont('Helvetica', 11.5 if per <= 6 else 10)
            c.drawString(bx, by - 5, r['subject'])
            if show.get('grades'):
                _badge(c, bx + col_w - 40, by - 5, 11, r['grade'])
            c.setStrokeColor(colors.HexColor('#9ca3af')); c.setLineWidth(0.6); c.setDash(1, 2.2)
            c.line(bx + _sw(r['subject'], 'Helvetica', 11) + 8, by - 6, bx + col_w - 56, by - 6); c.setDash()
        y = top - per * rh - 12
    # bottom: signature / seal / date
    by = m + 54
    if show.get('principal_name') or show.get('principal_signature'):
        lx = m + 90
        sig = ctx['official'].get('signature_path') if show.get('principal_signature') else None
        if sig:
            try:
                c.drawImage(sig, lx - 45, by + 4, 90, 24, preserveAspectRatio=True, anchor='s', mask='auto')
            except Exception:
                pass
        c.setStrokeColor(CHAR); c.setLineWidth(0.8); c.line(lx - 70, by, lx + 70, by)
        c.setFillColor(CHAR); c.setFont('Helvetica-Bold', 10)
        if show.get('principal_name'):
            c.drawCentredString(lx, by - 13, (ctx['official'].get('principal_name') or '').upper())
        c.setFillColor(MUTE); c.setFont('Helvetica', 8.5); c.drawCentredString(lx, by - 24, 'Principal')
    if show.get('school_stamp'):
        _seal(c, cx, by + 6, 30, ctx['school'].get('name'))
    if show.get('date_issued'):
        rx = W - m - 90
        c.setStrokeColor(CHAR); c.setLineWidth(0.8); c.line(rx - 70, by, rx + 70, by)
        c.setFillColor(CHAR); c.setFont('Helvetica-Bold', 10); c.drawCentredString(rx, by - 13, _issue_date().strftime('%d %B %Y'))
        c.setFillColor(MUTE); c.setFont('Helvetica', 8.5); c.drawCentredString(rx, by - 24, 'Date of Issue')


# ===========================================================================
#  Design 5 — CONTEMPORARY REPORT (emerald sidebar + stat tiles, portrait)
# ===========================================================================
def _draw_contemporary(c, ctx, show, cfg, verify_url):
    W, H = A4
    EMER = colors.HexColor('#065f46'); EMER_D = colors.HexColor('#064e3b')
    INK = colors.HexColor('#0f172a'); MUTE = colors.HexColor('#64748b')
    PAL = {'dist': colors.HexColor('#059669'), 'credit': colors.HexColor('#0284c7'),
           'pass': colors.HexColor('#d97706'), 'fail': colors.HexColor('#dc2626')}
    c.setFillColor(colors.white); c.rect(0, 0, W, H, fill=1, stroke=0)
    # sidebar
    sb_x, sb_w = 24, 196
    c.setFillColor(EMER); c.roundRect(sb_x, 24, sb_w, H - 48, 14, stroke=0, fill=1)
    scx = sb_x + sb_w / 2; sy = H - 48
    if show.get('school_logo') and ctx['school'].get('logo_path'):
        try:
            c.drawImage(ctx['school']['logo_path'], scx - 22, sy - 34, 44, 44, preserveAspectRatio=True, anchor='c', mask='auto')
        except Exception:
            pass
        sy -= 52
    if show.get('student_photo') and ctx['student'].get('photo_path'):
        _circle_photo(c, ctx['student']['photo_path'], scx, sy - 44, 44, colors.white, 3); sy -= 100
    if show.get('student_name'):
        for ln in _wrap(c, ctx['student']['name'], 'Helvetica-Bold', 15, sb_w - 24)[:3]:
            c.setFillColor(colors.white); c.setFont('Helvetica-Bold', 15); c.drawCentredString(scx, sy, ln); sy -= 18
    for l, v in _student_pairs(ctx, show)[:3]:
        c.setFillColor(colors.HexColor('#a7f3d0')); c.setFont('Helvetica', 8.5)
        c.drawCentredString(scx, sy, f'{l}: {v}'); sy -= 13
    # stat tiles
    sy -= 8
    st = ctx['stats']
    tiles = []
    if show.get('total_subjects'):
        tiles.append(('Subjects', st['total']))
    if show.get('credits'):
        tiles.append(('Credits', st['credits']))
    if show.get('a1_count'):
        tiles.append(('A1 grades', st['a1']))
    if show.get('average'):
        tiles.append(('Average', st['average']))
    if show.get('classification'):
        tiles.append(('Class', st['classification']))
    for l, v in tiles:
        _stat_tile(c, sb_x + 14, sy - 42, sb_w - 28, 40, l, v, EMER_D,
                   colors.HexColor('#6ee7b7'), colors.white)
        sy -= 48
    # main area
    mx0, mx1 = sb_x + sb_w + 22, W - 30
    my = H - 54
    if show.get('school_name'):
        for ln in _wrap(c, ctx['school']['name'], 'Helvetica-Bold', 20, mx1 - mx0)[:2]:
            c.setFillColor(INK); c.setFont('Helvetica-Bold', 20); c.drawString(mx0, my, ln); my -= 22
    if show.get('branch') and ctx.get('branch'):
        c.setFillColor(MUTE); c.setFont('Helvetica', 10); c.drawString(mx0, my, ctx['branch']); my -= 14
    c.setFillColor(EMER); c.setFont('Helvetica-Bold', 12)
    label = (ctx['exam']['short'] + ' ' if show.get('exam_name') else '') + (str(ctx['exam']['year']) if show.get('exam_year') else '') + ' Result'
    c.drawString(mx0, my - 4, label.strip()); my -= 24
    # results table with pills
    if show.get('subjects') and ctx['results']:
        n = len(ctx['results']); rh = 30 if n <= 9 else (26 if n <= 11 else 22)
        for i, r in enumerate(ctx['results']):
            if i % 2:
                c.setFillColor(colors.HexColor('#f1f5f9')); c.roundRect(mx0, my - rh + 3, mx1 - mx0, rh - 3, 6, stroke=0, fill=1)
            c.setFillColor(INK); c.setFont('Helvetica', 11.5 if n <= 11 else 10)
            c.drawString(mx0 + 12, my - rh / 2 - 3, r['subject'])
            if show.get('grade_desc') and r.get('desc'):
                sw = _sw(r['subject'], 'Helvetica', 11.5 if n <= 11 else 10)
                c.setFillColor(MUTE); c.setFont('Helvetica', 8.5); c.drawString(mx0 + 12 + sw + 8, my - rh / 2 - 3, r['desc'])
            if show.get('grades'):
                _pill(c, mx1 - 46, my - rh / 2 - 9, 40, 19, r['grade'], _band_color(r['grade'], PAL), fs=10.5)
            my -= rh
        my -= 30
    # signature / date / seal — kept clear of the table
    fy = max(70, my)
    # seal on the right, fully below the table
    if show.get('school_stamp'):
        _seal(c, mx1 - 30, fy - 12, 20, ctx['school'].get('name'))
        if show.get('date_issued'):
            c.setFillColor(MUTE); c.setFont('Helvetica', 8.5)
            c.drawRightString(mx1, fy - 48, 'Issued ' + _issue_date().strftime('%d %b %Y'))
    elif show.get('date_issued'):
        c.setFillColor(MUTE); c.setFont('Helvetica', 8.5)
        c.drawRightString(mx1, fy - 4, 'Issued ' + _issue_date().strftime('%d %b %Y'))
    if show.get('principal_name') or show.get('principal_signature'):
        sig = ctx['official'].get('signature_path') if show.get('principal_signature') else None
        if sig:
            try:
                c.drawImage(sig, mx0, fy + 2, 84, 22, preserveAspectRatio=True, anchor='sw', mask='auto')
            except Exception:
                pass
        c.setStrokeColor(INK); c.setLineWidth(0.8); c.line(mx0, fy, mx0 + 140, fy)
        c.setFillColor(INK); c.setFont('Helvetica-Bold', 10)
        if show.get('principal_name'):
            c.drawString(mx0, fy - 13, (ctx['official'].get('principal_name') or '').upper())
        c.setFillColor(MUTE); c.setFont('Helvetica', 8.5); c.drawString(mx0, fy - 24, 'Principal')


# ===========================================================================
#  Design 6 — CREATIVE ACADEMIC (duo-tone geometry, portrait)
# ===========================================================================
def _draw_creative(c, ctx, show, cfg, verify_url):
    W, H = A4
    PURP = colors.HexColor('#5b21b6'); ORANGE = colors.HexColor('#f97316')
    INK = colors.HexColor('#111827'); MUTE = colors.HexColor('#6b7280')
    PAL = {'dist': PURP, 'credit': colors.HexColor('#7c3aed'), 'pass': ORANGE, 'fail': colors.HexColor('#dc2626')}
    c.setFillColor(colors.white); c.rect(0, 0, W, H, fill=1, stroke=0)
    # geometric header
    hh = 210
    c.setFillColor(PURP)
    p = c.beginPath(); p.moveTo(0, H); p.lineTo(W, H); p.lineTo(W, H - hh + 40); p.lineTo(0, H - hh); p.close()
    c.drawPath(p, fill=1, stroke=0)
    c.saveState(); c.setFillAlpha(0.35); c.setFillColor(ORANGE); c.circle(W - 70, H - 60, 60, stroke=0, fill=1); c.restoreState()
    c.setFillColor(ORANGE); c.circle(W - 70, H - 60, 30, stroke=0, fill=1)
    if show.get('exam_year'):
        c.setFillColor(colors.white); c.setFont('Helvetica-Bold', 15); c.drawCentredString(W - 70, H - 66, str(ctx['exam']['year']))
    if show.get('school_logo') and ctx['school'].get('logo_path'):
        try:
            c.drawImage(ctx['school']['logo_path'], 44, H - 76, 44, 44, preserveAspectRatio=True, anchor='c', mask='auto')
        except Exception:
            pass
    tx = 100 if (show.get('school_logo') and ctx['school'].get('logo_path')) else 44
    ny = H - 58
    if show.get('school_name'):
        for ln in _wrap(c, ctx['school']['name'], 'Helvetica-Bold', 24, W - tx - 150)[:2]:
            c.setFillColor(colors.white); c.setFont('Helvetica-Bold', 24); c.drawString(tx, ny, ln); ny -= 26
    if show.get('exam_name'):
        c.setFillColor(colors.HexColor('#ddd6fe')); c.setFont('Helvetica', 9); c.drawString(tx, ny, ctx['exam']['name'])
    # circular photo overlapping
    cyp = H - hh - 4
    text_x = 44
    if show.get('student_photo') and ctx['student'].get('photo_path'):
        _circle_photo(c, ctx['student']['photo_path'], 88, cyp - 6, 44, ORANGE, 4); text_x = 150
    c.setFillColor(MUTE); c.setFont('Helvetica-Bold', 9); c.drawString(text_x, cyp + 24, 'CANDIDATE')
    if show.get('student_name'):
        for ln in _wrap(c, ctx['student']['name'], 'Helvetica-Bold', 20, W - text_x - 44)[:2]:
            c.setFillColor(INK); c.setFont('Helvetica-Bold', 20); c.drawString(text_x, cyp + 2, ln); cyp -= 22
    pairs = _student_pairs(ctx, show)
    if pairs:
        c.setFillColor(MUTE); c.setFont('Helvetica', 9); c.drawString(text_x, cyp - 6, '   '.join(f'{l}: {v}' for l, v in pairs[:3]))
    # results as a bold grid of badge rows
    y = min(cyp - 44, H - hh - 96)
    x0, x1 = 44, W - 44
    if show.get('subjects') and ctx['results']:
        n = len(ctx['results']); rh = 34 if n <= 9 else (28 if n <= 11 else 24)
        for r in ctx['results']:
            c.setFillColor(_band_color(r['grade'], PAL)); c.circle(x0 + 5, y - 6, 3.2, stroke=0, fill=1)
            c.setFillColor(INK); c.setFont('Helvetica-Bold', 13 if n <= 11 else 11); c.drawString(x0 + 18, y - 10, r['subject'])
            if show.get('grade_desc') and r.get('desc'):
                sw = _sw(r['subject'], 'Helvetica-Bold', 13 if n <= 11 else 11)
                c.setFillColor(MUTE); c.setFont('Helvetica-Oblique', 9); c.drawString(x0 + 18 + sw + 8, y - 10, r['desc'])
            if show.get('grades'):
                col = _band_color(r['grade'], PAL)
                c.setFillColor(col); c.circle(x1 - 14, y - 8, 13, stroke=0, fill=1)
                c.setFillColor(colors.white); c.setFont('Helvetica-Bold', 11); c.drawCentredString(x1 - 14, y - 12, r['grade'])
            c.setStrokeColor(colors.HexColor('#ececf3')); c.setLineWidth(1); c.line(x0 + 18, y - rh + 10, x1 - 34, y - rh + 10)
            y -= rh
        y -= 10
    # stat chips
    st = ctx['stats']; chips = []
    if show.get('credits'):
        chips.append(('Credits', st['credits']))
    if show.get('a1_count'):
        chips.append(('A1', st['a1']))
    if show.get('average'):
        chips.append(('Avg', st['average']))
    if show.get('classification'):
        chips.append(('Class', st['classification']))
    if chips:
        cxp = x0
        for l, v in chips:
            txt = f'{l}: {v}'; w = _sw(txt, 'Helvetica-Bold', 9) + 20
            _pill(c, cxp, y - 18, w, 20, txt, colors.HexColor('#f3e8ff'), tc=PURP, fs=9)
            cxp += w + 8
        y -= 30
    # footer
    fy = max(54, y - 4)
    if show.get('principal_name') or show.get('principal_signature'):
        sig = ctx['official'].get('signature_path') if show.get('principal_signature') else None
        if sig:
            try:
                c.drawImage(sig, x0, fy + 2, 84, 22, preserveAspectRatio=True, anchor='sw', mask='auto')
            except Exception:
                pass
        c.setStrokeColor(INK); c.setLineWidth(0.8); c.line(x0, fy, x0 + 140, fy)
        c.setFillColor(INK); c.setFont('Helvetica-Bold', 10)
        if show.get('principal_name'):
            c.drawString(x0, fy - 13, (ctx['official'].get('principal_name') or '').upper())
        c.setFillColor(MUTE); c.setFont('Helvetica', 8.5); c.drawString(x0, fy - 24, 'Principal')
    if show.get('school_stamp'):
        _seal(c, x1 - 30, fy + 4, 24, ctx['school'].get('name'))
    if show.get('date_issued'):
        c.setFillColor(MUTE); c.setFont('Helvetica', 8.5); c.drawRightString(x1, fy - 30, 'Issued ' + _issue_date().strftime('%d %b %Y'))
    # corner geometry accent
    c.setFillColor(PURP)
    p = c.beginPath(); p.moveTo(0, 0); p.lineTo(60, 0); p.lineTo(0, 60); p.close(); c.drawPath(p, fill=1, stroke=0)


# ===========================================================================
#  Design 7 — EXECUTIVE ACADEMIC 2026 (premium academic publication, portrait)
#  A crested serif masthead, an editorial WASSCE|year headline, a deep-navy
#  candidate band with an integrated photo, a ruled subject/grade ledger with a
#  column rule + faint crest watermark, a stat summary band, and a formal
#  seal + verification/QR authentication row. Every zone flows top-down (header,
#  exam, band, ledger) or is anchored to the base (summary, authentication,
#  footer), so hiding any optional component rebalances rather than leaving holes.
# ===========================================================================
def _draw_executive(c, ctx, show, cfg, verify_url):
    from reportlab.lib.utils import ImageReader
    W, H = TEMPLATES['executive'].get('pagesize', A4)
    NAVY = colors.HexColor('#17233f'); NAVY_BAND = colors.HexColor('#182644')
    CREAM = colors.HexColor('#f6f2e8'); GOLD = colors.HexColor('#b0914e')
    GOLD_LT = colors.HexColor('#caa964'); CHAR = colors.HexColor('#2c2f36')
    MUTE = colors.HexColor('#8b9099'); HAIR = colors.HexColor('#d9d4c6')
    BAND = colors.HexColor('#e8e4d8'); DIVL = colors.HexColor('#cfcbbd')
    cx = W / 2.0
    st = ctx['stats']
    logo = ctx['school'].get('logo_path') if show.get('school_logo') else None

    def _spaced_fit(text, font, size, x0, x1, y):
        """Draw TEXT left-justified across [x0, x1] with even letter-spacing
        (shrinking the font first if the run is naturally wider than the box)."""
        nat = sum(_sw(ch, font, size) for ch in text)
        box = x1 - x0
        if nat > box:
            size = size * box / nat; nat = box
        extra = (box - nat) / max(len(text) - 1, 1)
        c.setFont(font, size); xx = x0
        for ch in text:
            c.drawString(xx, y, ch); xx += _sw(ch, font, size) + extra

    # ---- page, frame, corner accent ----
    c.setFillColor(CREAM); c.rect(0, 0, W, H, fill=1, stroke=0)
    FM = 22
    c.setStrokeColor(NAVY); c.setLineWidth(1.3); c.rect(FM, FM, W - 2 * FM, H - 2 * FM, stroke=1, fill=0)
    c.setStrokeColor(GOLD); c.setLineWidth(0.6); c.rect(FM + 5, FM + 5, W - 2 * FM - 10, H - 2 * FM - 10, stroke=1, fill=0)
    tri = 48
    c.setFillColor(GOLD)
    p = c.beginPath(); p.moveTo(W - FM, H - FM); p.lineTo(W - FM - tri, H - FM); p.lineTo(W - FM, H - FM - tri); p.close()
    c.drawPath(p, fill=1, stroke=0)
    M, R = 46, W - 46

    # ---- ZONE 1 · school identity ----
    name_x = M
    if logo:
        try:
            c.drawImage(logo, M, H - FM - 12 - 70, 70, 70, preserveAspectRatio=True, anchor='nw', mask='auto')
            name_x = M + 70 + 18
        except Exception:
            name_x = M
    right_w = 154
    if show.get('school_name') and ctx['school'].get('name'):
        ny = H - 62
        for ln in _wrap(c, ctx['school']['name'].upper(), 'Times-Bold', 33, R - name_x - right_w)[:2]:
            c.setFillColor(NAVY); c.setFont('Times-Bold', 33); c.drawString(name_x, ny, ln); ny -= 36
    ry = H - 58
    if show.get('branch') and ctx.get('branch'):
        c.setFillColor(NAVY); c.setFont('Helvetica-Bold', 12.5); c.drawRightString(R, ry, ctx['branch']); ry -= 18
    if show.get('school_motto') and ctx['school'].get('motto'):
        c.setFillColor(MUTE); c.setFont('Helvetica-Oblique', 9); c.drawRightString(R, ry, 'School Motto'); ry -= 13
        for ln in _wrap(c, ctx['school']['motto'], 'Helvetica-Bold', 10.5, right_w)[:2]:
            c.setFillColor(NAVY); c.setFont('Helvetica-Bold', 10.5); c.drawRightString(R, ry, ln); ry -= 13
    hy = H - 144
    c.setStrokeColor(NAVY); c.setLineWidth(1.1); c.line(M, hy, R, hy)
    c.setStrokeColor(GOLD); c.setLineWidth(0.6); c.line(M, hy - 4, R, hy - 4)

    # ---- ZONE 2 · examination identity ----
    if show.get('exam_name'):
        c.setFillColor(NAVY)
        _spaced_fit('WEST AFRICAN SENIOR SCHOOL CERTIFICATE EXAMINATION', 'Helvetica-Bold', 12.5, M, R, hy - 30)
        big_y = hy - 82
        c.setFillColor(NAVY); c.setFont('Helvetica-Bold', 55); c.drawString(M, big_y, 'WASSCE')
        ww = _sw('WASSCE', 'Helvetica-Bold', 55)
        if show.get('exam_year'):
            yr = str(ctx['exam']['year'])
            wyr = _sw(yr, 'Helvetica-Bold', 55)
            c.setFillColor(GOLD); c.setFont('Helvetica-Bold', 55); c.drawString(R - wyr, big_y, yr)  # right-aligned → full width
            divx = M + ww + (R - wyr - (M + ww)) / 2.0                                                 # divider centred in the gap
            c.setStrokeColor(GOLD); c.setLineWidth(1.8); c.line(divx, big_y - 6, divx, big_y + 44)
    edy = hy - 100
    c.setStrokeColor(NAVY); c.setLineWidth(1.1); c.line(M, edy, R, edy)

    # ---- ZONE 3 · student identity (navy candidate band) ----
    band_top = edy - 14; band_h = 118; band_bot = band_top - band_h
    c.setFillColor(NAVY_BAND); c.rect(M, band_bot, R - M, band_h, fill=1, stroke=0)
    c.setStrokeColor(GOLD); c.setLineWidth(1.4); c.line(M, band_bot, R, band_bot)
    txt_x = M + 24
    name_w = R - 24 - txt_x
    if show.get('student_photo') and ctx['student'].get('photo_path'):
        pw, ph = 90, 108
        px = R - pw - 16; py = band_bot + (band_h - ph) / 2.0
        c.setFillColor(GOLD); c.rect(px - 3, py - 3, pw + 6, ph + 6, fill=1, stroke=0)
        try:
            c.drawImage(ctx['student']['photo_path'], px, py, pw, ph, preserveAspectRatio=True, anchor='c', mask='auto')
        except Exception:
            c.setFillColor(colors.HexColor('#e5e7eb')); c.rect(px, py, pw, ph, fill=1, stroke=0)
        name_w = px - 22 - txt_x
    if show.get('student_name'):
        nY = band_top - 40
        for ln in _wrap(c, ctx['student']['name'].upper(), 'Helvetica-Bold', 32, name_w)[:2]:
            c.setFillColor(colors.white); c.setFont('Helvetica-Bold', 32); c.drawString(txt_x, nY, ln); nY -= 35
    cand = ctx['student'].get('candidate_no')
    if show.get('candidate_no') and cand:
        c.setFillColor(GOLD_LT); c.setFont('Helvetica-Bold', 11)
        c.drawString(txt_x, band_bot + 26, (cfg.get('candidate_label') or 'Candidate No.'))
        c.setFillColor(colors.white); c.setFont('Helvetica-Bold', 15); c.drawString(txt_x, band_bot + 10, str(cand))

    # ---- bottom-anchored zones (compute anchors, draw ledger between) ----
    stats = []
    if show.get('total_subjects'): stats.append((st['total'], 'SUBJECTS'))
    if show.get('a1_count'):       stats.append((st['a1'], 'A1 GRADES'))
    if show.get('credits'):        stats.append((st['credits'], 'CREDITS'))
    if show.get('average'):        stats.append((st['average'], 'AVERAGE'))
    if show.get('classification'): stats.append((st['classification'], 'CLASS'))
    foot_div_y = FM + 48
    auth_top = foot_div_y + 84
    summary_h = 56 if stats else 0
    band_y0 = auth_top + 16
    results_bottom = (band_y0 + summary_h + 14) if stats else (auth_top + 14)

    # ---- ZONE 4 · academic results (ruled ledger) ----
    ry2 = band_bot - 26
    if show.get('subjects'):
        c.setFillColor(MUTE); c.setFont('Helvetica-Bold', 11); c.drawString(M, ry2, 'SUBJECTS')
        if show.get('grades'):
            c.drawRightString(R, ry2, 'GRADES')
        c.setStrokeColor(NAVY); c.setLineWidth(1.0); c.line(M, ry2 - 10, R, ry2 - 10)
    rows_top = ry2 - 10
    results = ctx['results']
    n = len(results)

    # faint crest watermark centred behind the ledger
    if logo and show.get('subjects'):
        wm = _faded(logo, 0.05)
        if wm:
            sz = 300
            try:
                c.drawImage(wm, cx - sz / 2, (rows_top + results_bottom) / 2 - sz / 2, sz, sz,
                            preserveAspectRatio=True, anchor='c', mask='auto')
            except Exception:
                pass

    def _col(items, x0, x1, y0, rh):
        subj_fs = 15 if rh >= 20 else 13
        gx = x1 - 56
        if show.get('grades') and items:
            c.setStrokeColor(HAIR); c.setLineWidth(0.9)
            c.line(gx, y0 - len(items) * rh + rh * 0.30, gx, y0 - rh * 0.10)
        yy = y0
        for r in items:
            base = yy - rh * 0.64
            if show.get('subjects'):
                c.setFillColor(CHAR); c.setFont('Times-Roman', subj_fs)
                c.drawString(x0, base, r['subject'])
                sw = _sw(r['subject'], 'Times-Roman', subj_fs)
                if show.get('grade_desc') and r.get('desc'):
                    c.setFillColor(MUTE); c.setFont('Helvetica', subj_fs - 6); c.drawString(x0 + sw + 10, base, r['desc'])
                else:
                    c.setFillColor(GOLD); c.setFont('Times-Roman', subj_fs); c.drawString(x0 + sw + 8, base, '—')
            if show.get('grades'):
                c.setFillColor(NAVY); c.setFont('Times-Bold', subj_fs + 4); c.drawRightString(x1, base, r['grade'])
            c.setStrokeColor(HAIR); c.setLineWidth(0.8); c.line(x0, yy - rh, x1, yy - rh)
            yy -= rh

    if show.get('subjects') and n:
        avail = rows_top - results_bottom
        if avail / n < 19 and n > 9:                     # dense → two legible columns
            per = (n + 1) // 2
            rh = min(30, max(16, avail / per))
            gap = 26; colw = (R - M - gap) / 2.0
            _col(results[:per], M, M + colw, rows_top, rh)
            _col(results[per:], M + colw + gap, R, rows_top, rh)
        else:
            rh = min(36, max(18, avail / n))
            _col(results, M, R, rows_top, rh)

    # ---- ZONE 6 · result summary band ----
    if stats:
        c.setFillColor(BAND); c.rect(M, band_y0, R - M, summary_h, fill=1, stroke=0)
        colw = (R - M) / len(stats)
        for i, (v, l) in enumerate(stats):
            sxc = M + colw * i + colw / 2.0
            c.setFillColor(NAVY); c.setFont('Times-Bold', 28); c.drawCentredString(sxc, band_y0 + summary_h - 34, str(v))
            c.setFillColor(NAVY); c.setFont('Helvetica-Bold', 10.5); c.drawCentredString(sxc, band_y0 + 12, l)
            if i:
                c.setStrokeColor(DIVL); c.setLineWidth(1.0)
                c.line(M + colw * i, band_y0 + 11, M + colw * i, band_y0 + summary_h - 11)

    # ---- ZONE 7 · official authentication ----
    az = auth_top - 4
    if show.get('principal_signature') or show.get('principal_name'):
        line_y = az - 40
        sig = ctx['official'].get('signature_path') if show.get('principal_signature') else None
        if sig:
            try:
                c.drawImage(sig, M, line_y + 4, 108, 28, preserveAspectRatio=True, anchor='sw', mask='auto')
            except Exception:
                sig = None
        if not sig:
            c.setFillColor(NAVY); c.setFont('Times-Italic', 22)
            c.drawString(M, line_y + 6, (ctx['official'].get('principal_name') or 'Principal'))
        c.setStrokeColor(NAVY); c.setLineWidth(1.0); c.line(M, line_y, M + 165, line_y)
        c.setFillColor(CHAR); c.setFont('Helvetica-Bold', 11); c.drawString(M, line_y - 15, 'Principal')
    if show.get('school_stamp'):
        _seal(c, cx, az - 34, 36, ctx['school'].get('name'))
    if show.get('verification_code') or show.get('qr_code') or show.get('date_issued'):
        qr_ok = False
        if show.get('qr_code') and verify_url:
            try:
                import qrcode
                qb = io.BytesIO(); qrcode.make(verify_url).save(qb, format='PNG'); qb.seek(0)
                c.drawImage(ImageReader(qb), R - 56, az - 58, 54, 54, mask='auto'); qr_ok = True
            except Exception:
                qr_ok = False
        vxr = (R - 56 - 14) if qr_ok else R
        if show.get('verification_code') and ctx.get('verify_code'):
            c.setFillColor(MUTE); c.setFont('Helvetica-Bold', 10); c.drawRightString(vxr, az - 20, 'Verification code')
            c.setFillColor(NAVY); c.setFont('Helvetica-Bold', 14); c.drawRightString(vxr, az - 36, str(ctx['verify_code']))
        if show.get('date_issued'):
            c.setFillColor(MUTE); c.setFont('Helvetica', 9.5)
            c.drawRightString(vxr, az - 52, 'Issued ' + _issue_date().strftime('%d %b %Y'))

    # ---- ZONE 8 · footer + bottom accent bars ----
    c.setFillColor(NAVY); c.rect(M, FM + 22, (R - M) * 0.62, 8, fill=1, stroke=0)
    c.setFillColor(GOLD); c.rect(M + (R - M) * 0.62, FM + 22, (R - M) * 0.38, 8, fill=1, stroke=0)
    c.setStrokeColor(HAIR); c.setLineWidth(1.0); c.line(M, foot_div_y, R, foot_div_y)
    name_addr = ctx['school'].get('name', '') or ''
    if show.get('school_address') and ctx['school'].get('address'):
        name_addr = (name_addr + ', ' + ctx['school']['address']).strip(', ')
    phone = ctx['school'].get('phone') if show.get('footer_contact') else None
    web = ctx['school'].get('website') if show.get('footer_website') else None
    if show.get('footer_custom') and cfg.get('footer_text'):
        name_addr = cfg['footer_text']
    segs = [s for s in [name_addr or None, phone, web] if s]
    if segs:
        c.setFont('Helvetica', 9.5); c.setFillColor(NAVY); fy = FM + 44
        if len(segs) >= 3:
            c.drawString(M, fy, segs[0]); c.drawCentredString(cx, fy, segs[1]); c.drawRightString(R, fy, segs[2])
        elif len(segs) == 2:
            c.drawString(M, fy, segs[0]); c.drawRightString(R, fy, segs[1])
        else:
            c.drawCentredString(cx, fy, segs[0])


def _sw(text, font, size):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    return stringWidth(text, font, size)


_CANVAS_DRAW = {
    'prestige': _draw_prestige, 'classic': _draw_classic, 'editorial': _draw_editorial,
    'premium': _draw_premium, 'contemporary': _draw_contemporary, 'creative': _draw_creative,
    'executive': _draw_executive,
}


def _render_canvas(ctx, key, show, cfg, verify_url):
    from reportlab.pdfgen import canvas as _canvas
    buf = io.BytesIO()
    tpl = TEMPLATES.get(key, TEMPLATES[DEFAULT_TEMPLATE])
    pagesize = tuple(tpl['pagesize']) if tpl.get('pagesize') else (landscape(A4) if is_landscape(key) else A4)
    c = _canvas.Canvas(buf, pagesize=pagesize)
    c.setTitle(f"WAEC {ctx['exam']['year']} — {ctx['student']['name']}")
    _CANVAS_DRAW[key](c, ctx, show, cfg, verify_url)
    c.showPage(); c.save()
    buf.seek(0)
    return buf


def render_pdf(ctx, template_key, show, cfg=None, verify_url=None):
    """Deterministically render the result to a PDF (BytesIO). Every template is
    canvas-drawn (see _CANVAS_DRAW)."""
    cfg = cfg or {}
    key = template_key if template_key in _CANVAS_DRAW else DEFAULT_TEMPLATE
    return _render_canvas(ctx, key, show, cfg, verify_url)


def render_image(pdf_buf, fmt='png', scale=2.0):
    """Rasterise the first page of a rendered PDF to PNG/JPEG bytes (PyMuPDF)."""
    import fitz
    pdf_buf.seek(0)
    doc = fitz.open(stream=pdf_buf.read(), filetype='pdf')
    page = doc.load_page(0)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    fmt = (fmt or 'png').lower()
    if fmt in ('jpg', 'jpeg'):
        data = pix.tobytes('jpg')
    else:
        data = pix.tobytes('png')
    doc.close()
    return data


def render(ctx, template_key, show, cfg=None, fmt='pdf', verify_url=None, scale=2.0):
    """One entry point → bytes + mimetype + extension for any output format."""
    pdf = render_pdf(ctx, template_key, show, cfg, verify_url)
    fmt = (fmt or 'pdf').lower()
    if fmt == 'pdf':
        return pdf.getvalue(), 'application/pdf', 'pdf'
    if fmt in ('jpg', 'jpeg'):
        return render_image(pdf, 'jpg', scale), 'image/jpeg', 'jpg'
    return render_image(pdf, 'png', scale), 'image/png', 'png'
