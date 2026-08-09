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
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, Image, HRFlowable, KeepInFrame)

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
    'profile':      {'name': 'Academic Profile — 2026',
                     'desc': 'Minimalist institutional dossier: a vertical identity rail (monogram, '
                             'rotated WASSCE·year, photo, faint crest) beside a typographic record — '
                             'serif masthead, large student name, a numbered subject/grade list with '
                             'fine rules, a whitespace stat summary and a restrained seal/QR footer.',
                     'landscape': False},
    'meridian':     {'name': 'Meridian — 2026',
                     'desc': 'Contemporary institutional layout: an angular layered WASSCE·year badge, '
                             'a bevel-framed portrait, a large architectural result panel with numbered '
                             'rows and bold grades, a green stat bar and a framed seal/QR verification '
                             'row — geometric, asymmetric and expressive.',
                     'landscape': False},
    'aurelis':      {'name': 'Aurelis — 2026',
                     'desc': 'Editorial serif publication: a right-aligned crest masthead, ruled '
                             'WASSCE·year band, an oversized multi-line student name beside a '
                             'crop-marked portrait, a two-column bordered subject/grade matrix with a '
                             'faint watermark, a centred achievement line and a signature/seal/QR '
                             'verification block over a three-column label row.',
                     'landscape': False},
    'monument':     {'name': 'Monument — 2026',
                     'desc': 'Premium institutional annual-report: an asymmetric crest-and-name '
                             'masthead with a right-aligned WASSCE·year identity joined by a fine '
                             'gold rule, a vertical WASSCE margin marker, a compact examination '
                             'label, an oversized serif student name beside a framed portrait, a '
                             'three-column NUMBER/SUBJECT/GRADE record with banded rows, an '
                             'editorial stat line and a signature / teal seal / verification+QR row.',
                     'landscape': False},
    'terrain':      {'name': 'Terrain — 2026',
                     'desc': 'Contemporary architectural layout inspired by African modernism: a '
                             'split masthead with a plum block and large serif year, a warm-sand '
                             'field, an oversized deep-plum student name over a faint cropped year '
                             'motif beside an offset-framed portrait, an editorial number/subject/'
                             'grade record over hairline rules, a plum-and-terracotta achievement '
                             'band, and a restrained signature / seal / QR verification row.',
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
        {'key': 'branch', 'label': 'Branch / Campus', 'default': False,
         'avail': lambda c: True},   # shows the branch name, or "Main Campus" when the school has none
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
    'profile':   {'label': 'Academic Profile (Full)',
                  'keys': ['school_name', 'school_logo', 'student_name', 'student_photo',
                           'candidate_no', 'exam_name', 'exam_year', 'subjects', 'grades',
                           'total_subjects', 'a1_count', 'credits',
                           'principal_name', 'principal_signature', 'school_stamp',
                           'verification_code', 'qr_code', 'date_issued',
                           'footer_contact', 'footer_website']},
    'meridian':  {'label': 'Meridian (Full)',
                  'keys': ['school_name', 'school_logo', 'branch', 'school_motto',
                           'student_name', 'student_photo', 'candidate_no',
                           'exam_name', 'exam_year', 'subjects', 'grades',
                           'total_subjects', 'a1_count', 'credits',
                           'principal_name', 'principal_signature', 'school_stamp',
                           'verification_code', 'qr_code', 'date_issued',
                           'footer_contact', 'footer_website']},
    'aurelis':   {'label': 'Aurelis (Full)',
                  'keys': ['school_name', 'school_logo', 'branch', 'school_motto',
                           'student_name', 'student_photo', 'candidate_no',
                           'exam_name', 'exam_year', 'subjects', 'grades',
                           'total_subjects', 'a1_count', 'credits',
                           'principal_name', 'principal_signature', 'school_stamp',
                           'verification_code', 'qr_code', 'date_issued',
                           'footer_contact', 'footer_website']},
    'monument':  {'label': 'Monument (Full)',
                  'keys': ['school_name', 'school_logo', 'branch',
                           'student_name', 'student_photo', 'candidate_no',
                           'exam_name', 'exam_year', 'subjects', 'grades',
                           'total_subjects', 'a1_count', 'credits',
                           'principal_name', 'principal_signature', 'school_stamp',
                           'verification_code', 'qr_code', 'date_issued',
                           'school_address', 'footer_contact', 'footer_website']},
    'terrain':   {'label': 'Terrain (Full)',
                  'keys': ['school_name', 'school_logo', 'branch',
                           'student_name', 'student_photo', 'candidate_no',
                           'exam_name', 'exam_year', 'subjects', 'grades',
                           'total_subjects', 'a1_count', 'credits',
                           'principal_name', 'principal_signature', 'school_stamp',
                           'verification_code', 'qr_code', 'date_issued',
                           'school_address', 'footer_contact', 'footer_website']},
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


# --------------------------------------------------------------------------- #
#  RENDERER — shared building blocks (component-flag aware)                    #
# --------------------------------------------------------------------------- #
def _styles(primary, accent):
    ss = getSampleStyleSheet()
    P = colors.HexColor(primary)
    A = colors.HexColor(accent)
    MUT = colors.HexColor('#64748b')
    return {
        'P': P, 'A': A, 'MUT': MUT,
        'school': ParagraphStyle('school', parent=ss['Title'], fontSize=19, leading=22,
                                 textColor=P, alignment=TA_CENTER, spaceAfter=0),
        'school_l': ParagraphStyle('school_l', parent=ss['Title'], fontSize=22, leading=24,
                                   textColor=P, alignment=TA_LEFT, spaceAfter=0),
        'motto': ParagraphStyle('motto', parent=ss['Italic'], fontSize=9.5, textColor=MUT, alignment=TA_CENTER),
        'muted': ParagraphStyle('muted', parent=ss['Normal'], fontSize=8.5, textColor=MUT, alignment=TA_CENTER),
        'muted_l': ParagraphStyle('muted_l', parent=ss['Normal'], fontSize=8.5, textColor=MUT, alignment=TA_LEFT),
        'title': ParagraphStyle('title', parent=ss['Heading2'], fontSize=13, textColor=A,
                                alignment=TA_CENTER, spaceBefore=6, spaceAfter=2, tracking=1),
        'label': ParagraphStyle('label', parent=ss['Normal'], fontSize=9, textColor=MUT),
        'val': ParagraphStyle('val', parent=ss['Normal'], fontSize=10.5, textColor=colors.HexColor('#0f172a')),
        'name': ParagraphStyle('name', parent=ss['Heading1'], fontSize=17, textColor=colors.HexColor('#0f172a')),
        'th': ParagraphStyle('th', parent=ss['Normal'], fontSize=9, textColor=colors.white, alignment=TA_LEFT),
        'td': ParagraphStyle('td', parent=ss['Normal'], fontSize=10, textColor=colors.HexColor('#0f172a')),
        'small': ParagraphStyle('small', parent=ss['Normal'], fontSize=8, textColor=MUT),
        'ss': ss,
    }


def _esc(v):
    from xml.sax.saxutils import escape
    return escape(str(v)) if v is not None else ''


def _logo_img(path, max_h=18 * mm, max_w=40 * mm):
    if not path:
        return None
    try:
        from PIL import Image as PILImage
        with PILImage.open(path) as im:
            iw, ih = im.size
        ratio = (iw / ih) if ih else 1.0
        h, w = max_h, max_h * ratio
        if w > max_w:
            w, h = max_w, max_w / ratio if ratio else max_h
        return Image(path, width=w, height=h)
    except Exception:
        return None


def _photo_img(ctx, cfg):
    p = ctx['student'].get('photo_path')
    if not p:
        return None
    sizes = {'small': 22 * mm, 'medium': 28 * mm, 'large': 36 * mm}
    side = sizes.get((cfg.get('student_photo') or {}).get('size', 'medium'), 28 * mm)
    try:
        return Image(p, width=side, height=side)
    except Exception:
        return None


def _qr_img(data, side=24 * mm):
    try:
        import qrcode
        img = qrcode.make(data)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return Image(buf, width=side, height=side)
    except Exception:
        return None


def _header_lines(ctx, show):
    """Contact/address/motto lines for the letterhead (respecting flags)."""
    s = ctx['school']
    lines = []
    if show.get('branch') and ctx.get('branch'):
        lines.append(('branch', ctx['branch']))
    if show.get('school_motto') and s.get('motto'):
        lines.append(('motto', s['motto']))
    contacts = []
    if show.get('school_address') and s.get('address'):
        contacts.append(s['address'])
    if show.get('school_phone') and s.get('phone'):
        contacts.append('Tel: ' + s['phone'])
    if show.get('school_email') and s.get('email'):
        contacts.append(s['email'])
    if show.get('school_website') and s.get('website'):
        contacts.append(s['website'])
    return lines, contacts


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


def _result_table(ctx, show, S, accent, compact=False):
    """The subjects/grades table — columns depend on flags; compact for density."""
    if not show.get('subjects'):
        return None
    cols = ['#', 'Subject']
    keys = []
    if show.get('grades'):
        cols.append('Grade'); keys.append('grade')
    if show.get('grade_desc'):
        cols.append('Remark'); keys.append('desc')
    if show.get('grade_points'):
        cols.append('Points'); keys.append('points')
    head = [Paragraph(f'<b>{_esc(c)}</b>', S['th']) for c in cols]
    data = [head]
    for i, r in enumerate(ctx['results'], 1):
        row = [Paragraph(str(i), S['td']), Paragraph(_esc(r['subject']), S['td'])]
        for k in keys:
            row.append(Paragraph(f'<b>{_esc(r[k])}</b>' if k == 'grade' else _esc(r[k]), S['td']))
        data.append(row)
    ncol = len(cols)
    widths = [10 * mm, None] + [22 * mm] * (ncol - 2)
    # distribute remaining width
    total_w = 165 * mm
    fixed = 10 * mm + 22 * mm * (ncol - 2)
    widths[1] = total_w - fixed
    pad = 3 if compact else 5
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), accent),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 1), (-1, -1), 9 if compact else 10),
        ('TOPPADDING', (0, 0), (-1, -1), pad), ('BOTTOMPADDING', (0, 0), (-1, -1), pad),
        ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f6f8fb')]),
        ('LINEBELOW', (0, 0), (-1, -1), 0.4, colors.HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return t


def _stats_strip(ctx, show, S, accent, width=165 * mm):
    st = ctx['stats']
    cells = []
    if show.get('total_subjects'):
        cells.append(('Subjects', st['total']))
    if show.get('a1_count'):
        cells.append(('A1 grades', st['a1']))
    if show.get('credits'):
        cells.append(('Credits', st['credits']))
    if show.get('average'):
        cells.append(('Average', st['average']))
    if show.get('classification'):
        cells.append(('Classification', st['classification']))
    if not cells:
        return None
    row = [[Paragraph(f'<font color="#ffffff" size=8>{_esc(l)}</font><br/>'
                      f'<font color="#ffffff" size=13><b>{_esc(v)}</b></font>', S['td'])
            for l, v in cells]]
    t = Table(row, colWidths=[width / len(cells)] * len(cells))
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), accent),
        ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEAFTER', (0, 0), (-2, -1), 0.5, colors.white),
    ]))
    return t


def _signatures(ctx, show, cfg, S):
    """Signature / stamp / date / verification row."""
    cols = []
    if show.get('principal_signature') or show.get('principal_name'):
        name = ctx['official'].get('principal_name') if show.get('principal_name') else ''
        cols.append(_sig_col(ctx['official'].get('signature_path') if show.get('principal_signature') else None,
                             'Principal', name, S))
    if show.get('exam_officer'):
        cols.append(_sig_col(None, 'Examination Officer', ctx['official'].get('exam_officer_name', ''), S))
    if show.get('school_stamp') and ctx['official'].get('stamp_path'):
        img = _logo_img(ctx['official']['stamp_path'], max_h=24 * mm, max_w=24 * mm)
        cols.append([img or Spacer(1, 24 * mm), Paragraph('School Stamp', S['small'])])
    if not cols:
        return None
    t = Table([[c for c in cols]], colWidths=[(165 * mm) / len(cols)] * len(cols))
    t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
                           ('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
    return t


def _sig_col(sig_path, role, name, S):
    top = _logo_img(sig_path, max_h=14 * mm, max_w=40 * mm) if sig_path else HRFlowable(
        width='70%', thickness=0.8, color=colors.HexColor('#94a3b8'), spaceBefore=14, spaceAfter=2)
    parts = [top]
    if not sig_path:
        parts = [Spacer(1, 12 * mm), HRFlowable(width='70%', thickness=0.8,
                 color=colors.HexColor('#94a3b8'), spaceAfter=2)]
    if name:
        parts.append(Paragraph(f'<b>{_esc(name)}</b>', ParagraphStyle('c', parent=S['td'], alignment=TA_CENTER)))
    parts.append(Paragraph(_esc(role), ParagraphStyle('r', parent=S['small'], alignment=TA_CENTER)))
    return parts


def _official_extras(ctx, show, S, verify_url):
    """Date issued / verification code / QR — returned as a list of small flowables."""
    import datetime
    out = []
    bits = []
    if show.get('date_issued'):
        bits.append('Issued: ' + datetime.date.today().strftime('%d %B %Y'))
    if show.get('verification_code') and ctx.get('verify_code'):
        bits.append('Verify code: ' + ctx['verify_code'])
    if bits:
        out.append(Paragraph(' &nbsp;•&nbsp; '.join(_esc(b) for b in bits),
                             ParagraphStyle('v', parent=S['small'], alignment=TA_CENTER)))
    if show.get('qr_code') and verify_url:
        qr = _qr_img(verify_url)
        if qr:
            out.append(Spacer(1, 3))
            out.append(qr)
    return out


def _footer(ctx, show, cfg, S):
    lines = []
    if show.get('footer_contact'):
        c = [x for x in [ctx['school'].get('phone'), ctx['school'].get('email')] if x]
        if c:
            lines.append(' | '.join(c))
    if show.get('footer_website') and ctx['school'].get('website'):
        lines.append(ctx['school']['website'])
    if show.get('footer_custom'):
        txt = (cfg.get('footer_custom') or {}).get('text')
        if txt:
            lines.append(txt)
    if show.get('footer_disclaimer'):
        lines.append('This document is a school-issued representation of results and is not a '
                     'substitute for the official WAEC statement of result.')
    if not lines:
        return None
    return Paragraph('<br/>'.join(_esc(l) for l in lines),
                     ParagraphStyle('f', parent=S['small'], alignment=TA_CENTER))


# --------------------------------------------------------------------------- #
#  TEMPLATE layouts — five distinct arrangements of the blocks above.         #
# --------------------------------------------------------------------------- #
def _centered_header(ctx, show, cfg, S):
    el = []
    if show.get('school_logo') and ctx['school'].get('logo_path'):
        lg = _logo_img(ctx['school']['logo_path'])
        if lg:
            lg.hAlign = 'CENTER'; el.append(lg); el.append(Spacer(1, 4))
    if show.get('school_name') and ctx['school'].get('name'):
        el.append(Paragraph(_esc(ctx['school']['name']), S['school']))
    lines, contacts = _header_lines(ctx, show)
    for kind, txt in lines:
        el.append(Paragraph(_esc(txt), S['motto'] if kind == 'motto' else S['muted']))
    if contacts:
        el.append(Paragraph(_esc(' | '.join(contacts)), S['muted']))
    return el


def _t_classic(ctx, show, cfg, S, verify_url):
    el = _centered_header(ctx, show, cfg, S)
    el.append(Spacer(1, 6))
    el.append(HRFlowable(width='100%', thickness=1.4, color=S['P']))
    el.append(HRFlowable(width='100%', thickness=0.5, color=S['P'], spaceBefore=2))
    el.append(Paragraph('STATEMENT OF EXAMINATION RESULT', S['title']))
    el.append(Spacer(1, 8))
    if show.get('student_name'):
        el.append(Paragraph(_esc(ctx['student']['name']),
                            ParagraphStyle('n', parent=S['name'], alignment=TA_CENTER)))
    pairs = _student_pairs(ctx, show)
    if pairs:
        line = '&nbsp;&nbsp;•&nbsp;&nbsp;'.join(f'<b>{_esc(l)}:</b> {_esc(v)}' for l, v in pairs)
        el.append(Paragraph(line, ParagraphStyle('p', parent=S['val'], alignment=TA_CENTER)))
    if show.get('student_photo'):
        ph = _photo_img(ctx, cfg)
        if ph:
            ph.hAlign = 'CENTER'; el.append(Spacer(1, 6)); el.append(ph)
    el.append(Spacer(1, 10))
    rt = _result_table(ctx, show, S, S['A'], compact=len(ctx['results']) >= 10)
    if rt:
        el.append(rt)
    ss = _stats_strip(ctx, show, S, S['P'])
    if ss:
        el.append(Spacer(1, 8)); el.append(ss)
    el.append(Spacer(1, 16))
    sig = _signatures(ctx, show, cfg, S)
    if sig:
        el.append(sig)
    for x in _official_extras(ctx, show, S, verify_url):
        el.append(x)
    ft = _footer(ctx, show, cfg, S)
    if ft:
        el.append(Spacer(1, 8)); el.append(ft)
    return el


def _t_editorial(ctx, show, cfg, S, verify_url):
    """Asymmetric: bold left masthead over a full-width rule, side-by-side identity."""
    el = []
    masthead = []
    if show.get('school_name'):
        masthead.append(Paragraph(_esc(ctx['school'].get('name', '')), S['school_l']))
    lines, contacts = _header_lines(ctx, show)
    for kind, txt in lines:
        masthead.append(Paragraph(_esc(txt), S['muted_l']))
    if contacts:
        masthead.append(Paragraph(_esc(' | '.join(contacts)), S['muted_l']))
    logo = _logo_img(ctx['school'].get('logo_path'), max_h=22 * mm, max_w=34 * mm) if show.get('school_logo') else None
    if logo:
        row = Table([[masthead, logo]], colWidths=[130 * mm, 35 * mm])
        row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                                 ('ALIGN', (1, 0), (1, 0), 'RIGHT')]))
        el.append(row)
    else:
        el.extend(masthead)
    el.append(HRFlowable(width='100%', thickness=3, color=S['A'], spaceBefore=6))
    el.append(Paragraph('<b>WAEC RESULT</b> &nbsp; <font color="#64748b" size=10>· '
                        f"{_esc(ctx['exam']['year'])}</font>",
                        ParagraphStyle('h', parent=S['title'], alignment=TA_LEFT, fontSize=15, textColor=S['P'])))
    el.append(Spacer(1, 6))
    # identity rail (photo left, name+pairs right)
    ident = []
    if show.get('student_name'):
        ident.append(Paragraph(_esc(ctx['student']['name']), S['name']))
    pairs = _student_pairs(ctx, show)
    for l, v in pairs:
        ident.append(Paragraph(f'<font color="#64748b" size=8>{_esc(l)}</font> &nbsp; <b>{_esc(v)}</b>', S['val']))
    ph = _photo_img(ctx, cfg) if show.get('student_photo') else None
    if ph:
        r = Table([[ph, ident]], colWidths=[32 * mm, 133 * mm])
        r.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        el.append(r)
    else:
        el.extend(ident)
    el.append(Spacer(1, 10))
    rt = _result_table(ctx, show, S, S['P'], compact=len(ctx['results']) >= 10)
    if rt:
        el.append(rt)
    ss = _stats_strip(ctx, show, S, S['A'])
    if ss:
        el.append(Spacer(1, 8)); el.append(ss)
    el.append(Spacer(1, 16))
    sig = _signatures(ctx, show, cfg, S)
    if sig:
        el.append(sig)
    for x in _official_extras(ctx, show, S, verify_url):
        el.append(x)
    ft = _footer(ctx, show, cfg, S)
    if ft:
        el.append(Spacer(1, 8)); el.append(ft)
    return el


def _t_premium(ctx, show, cfg, S, verify_url):
    """Landscape certificate: centred, generous spacing, seal area on the right."""
    el = _centered_header(ctx, show, cfg, S)
    el.append(Spacer(1, 4))
    el.append(HRFlowable(width='60%', thickness=1.2, color=S['A']))
    el.append(Paragraph('CERTIFICATE OF EXAMINATION RESULT', S['title']))
    el.append(Spacer(1, 6))
    if show.get('student_name'):
        el.append(Paragraph(_esc(ctx['student']['name']),
                            ParagraphStyle('n', parent=S['name'], alignment=TA_CENTER, fontSize=20)))
    pairs = _student_pairs(ctx, show)
    if pairs:
        line = '&nbsp;&nbsp;•&nbsp;&nbsp;'.join(f'<b>{_esc(l)}:</b> {_esc(v)}' for l, v in pairs)
        el.append(Paragraph(line, ParagraphStyle('p', parent=S['val'], alignment=TA_CENTER)))
    el.append(Spacer(1, 8))
    rt = _result_table(ctx, show, S, S['A'], compact=len(ctx['results']) >= 8)
    if rt:
        el.append(rt)
    ss = _stats_strip(ctx, show, S, S['P'])
    if ss:
        el.append(Spacer(1, 6)); el.append(ss)
    el.append(Spacer(1, 14))
    sig = _signatures(ctx, show, cfg, S)
    if sig:
        el.append(sig)
    for x in _official_extras(ctx, show, S, verify_url):
        el.append(x)
    ft = _footer(ctx, show, cfg, S)
    if ft:
        el.append(Spacer(1, 6)); el.append(ft)
    return el


def _t_contemporary(ctx, show, cfg, S, verify_url):
    """Two-panel card: left student panel, right results — modern report card."""
    el = _centered_header(ctx, show, cfg, S)
    el.append(HRFlowable(width='100%', thickness=1, color=S['P'], spaceBefore=6, spaceAfter=8))
    # left panel content
    left = []
    if show.get('student_photo'):
        ph = _photo_img(ctx, cfg)
        if ph:
            ph.hAlign = 'CENTER'; left.append(ph); left.append(Spacer(1, 6))
    if show.get('student_name'):
        left.append(Paragraph(_esc(ctx['student']['name']),
                              ParagraphStyle('n', parent=S['name'], fontSize=13, alignment=TA_CENTER)))
    for l, v in _student_pairs(ctx, show):
        left.append(Paragraph(f'<font color="#64748b" size=8>{_esc(l)}</font><br/><b>{_esc(v)}</b>',
                              ParagraphStyle('lp', parent=S['val'], alignment=TA_CENTER, spaceAfter=3)))
    right = []
    rt = _result_table_narrow(ctx, show, S)
    if rt:
        right.append(rt)
    ss = _stats_strip(ctx, show, S, S['A'], width=113 * mm)
    if ss:
        right.append(Spacer(1, 6)); right.append(ss)
    panel = Table([[left or [Spacer(1, 1)], right or [Spacer(1, 1)]]], colWidths=[52 * mm, 113 * mm])
    panel.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#f6f8fb')),
        ('BOX', (0, 0), (0, 0), 0.6, colors.HexColor('#e2e8f0')),
        ('LEFTPADDING', (0, 0), (0, 0), 10), ('RIGHTPADDING', (0, 0), (0, 0), 10),
        ('TOPPADDING', (0, 0), (0, 0), 12), ('BOTTOMPADDING', (0, 0), (0, 0), 12),
        ('LEFTPADDING', (1, 0), (1, 0), 12),
    ]))
    el.append(panel)
    el.append(Spacer(1, 16))
    sig = _signatures(ctx, show, cfg, S)
    if sig:
        el.append(sig)
    for x in _official_extras(ctx, show, S, verify_url):
        el.append(x)
    ft = _footer(ctx, show, cfg, S)
    if ft:
        el.append(Spacer(1, 8)); el.append(ft)
    return el


def _result_table_narrow(ctx, show, S):
    if not show.get('subjects'):
        return None
    cols = ['Subject']
    keys = []
    if show.get('grades'):
        cols.append('Grade'); keys.append('grade')
    if show.get('grade_desc'):
        cols.append('Remark'); keys.append('desc')
    data = [[Paragraph(f'<b>{_esc(c)}</b>', S['th']) for c in cols]]
    for r in ctx['results']:
        row = [Paragraph(_esc(r['subject']), S['td'])]
        for k in keys:
            row.append(Paragraph(f'<b>{_esc(r[k])}</b>' if k == 'grade' else _esc(r[k]), S['td']))
        data.append(row)
    w0 = 113 * mm - 22 * mm * (len(cols) - 1)
    t = Table(data, colWidths=[w0] + [22 * mm] * (len(cols) - 1), repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), S['P']),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f6f8fb')]),
        ('LINEBELOW', (0, 0), (-1, -1), 0.3, colors.HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return t


def _t_creative(ctx, show, cfg, S, verify_url):
    """Expressive: a solid accent header band with reversed-out school name."""
    el = []
    band = []
    inner = []
    if show.get('school_name'):
        inner.append(Paragraph(f'<font color="#ffffff">{_esc(ctx["school"].get("name",""))}</font>',
                               ParagraphStyle('sn', parent=S['school'], textColor=colors.white, alignment=TA_LEFT)))
    if show.get('school_motto') and ctx['school'].get('motto'):
        inner.append(Paragraph(f'<font color="#e2f5ee">{_esc(ctx["school"]["motto"])}</font>',
                               ParagraphStyle('sm', parent=S['muted_l'], textColor=colors.white)))
    logo = _logo_img(ctx['school'].get('logo_path'), max_h=18 * mm, max_w=28 * mm) if show.get('school_logo') else None
    cells = [[inner, logo or Spacer(1, 1)]]
    band_t = Table(cells, colWidths=[137 * mm, 28 * mm])
    band_t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), S['P']),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 14), ('RIGHTPADDING', (0, 0), (-1, -1), 14),
        ('TOPPADDING', (0, 0), (-1, -1), 12), ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    el.append(band_t)
    # accent sub-band with exam title
    sub = Table([[Paragraph(f'<font color="#ffffff"><b>WAEC RESULT · {_esc(ctx["exam"]["year"])}</b></font>',
                            ParagraphStyle('x', parent=S['td'], textColor=colors.white))]], colWidths=[165 * mm])
    sub.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), S['A']),
                             ('LEFTPADDING', (0, 0), (-1, -1), 14),
                             ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
    el.append(sub)
    el.append(Spacer(1, 10))
    ident = []
    if show.get('student_name'):
        ident.append(Paragraph(_esc(ctx['student']['name']), S['name']))
    pairs = _student_pairs(ctx, show)
    if pairs:
        ident.append(Paragraph('&nbsp;&nbsp;•&nbsp;&nbsp;'.join(
            f'<font color="#64748b" size=8>{_esc(l)}</font> <b>{_esc(v)}</b>' for l, v in pairs), S['val']))
    ph = _photo_img(ctx, cfg) if show.get('student_photo') else None
    if ph:
        r = Table([[ident, ph]], colWidths=[133 * mm, 32 * mm])
        r.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('ALIGN', (1, 0), (1, 0), 'RIGHT')]))
        el.append(r)
    else:
        el.extend(ident)
    el.append(Spacer(1, 10))
    rt = _result_table(ctx, show, S, S['P'], compact=len(ctx['results']) >= 10)
    if rt:
        el.append(rt)
    ss = _stats_strip(ctx, show, S, S['A'])
    if ss:
        el.append(Spacer(1, 8)); el.append(ss)
    el.append(Spacer(1, 16))
    sig = _signatures(ctx, show, cfg, S)
    if sig:
        el.append(sig)
    for x in _official_extras(ctx, show, S, verify_url):
        el.append(x)
    ft = _footer(ctx, show, cfg, S)
    if ft:
        el.append(Spacer(1, 8)); el.append(ft)
    return el


_LAYOUTS = {
    'classic': _t_classic, 'editorial': _t_editorial, 'premium': _t_premium,
    'contemporary': _t_contemporary, 'creative': _t_creative,
}


def _border_for(key, primary, accent):
    """A page decorator (drawn border) matching the template's character."""
    P = colors.HexColor(primary)
    A = colors.HexColor(accent)

    def paint(canvas, doc):
        w, h = doc.pagesize
        canvas.saveState()
        if key == 'classic':
            canvas.setStrokeColor(P); canvas.setLineWidth(2)
            canvas.rect(12 * mm, 12 * mm, w - 24 * mm, h - 24 * mm)
            canvas.setLineWidth(0.6)
            canvas.rect(15 * mm, 15 * mm, w - 30 * mm, h - 30 * mm)
        elif key == 'premium':
            canvas.setStrokeColor(A); canvas.setLineWidth(3)
            canvas.rect(10 * mm, 10 * mm, w - 20 * mm, h - 20 * mm)
            canvas.setStrokeColor(P); canvas.setLineWidth(0.8)
            canvas.rect(14 * mm, 14 * mm, w - 28 * mm, h - 28 * mm)
        elif key == 'creative':
            canvas.setFillColor(A)
            canvas.rect(0, 0, 6 * mm, h, fill=1, stroke=0)
        elif key == 'editorial':
            canvas.setFillColor(P)
            canvas.rect(0, h - 6 * mm, w, 6 * mm, fill=1, stroke=0)
        canvas.restoreState()
    return paint


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
    """A drawn official seal (concentric gold rings + centred initials)."""
    c.setStrokeColor(_GOLD); c.setLineWidth(1.4); c.circle(cx, cy, r, stroke=1, fill=0)
    c.setLineWidth(0.7); c.circle(cx, cy, r - 4, stroke=1, fill=0)
    c.setDash(1, 2); c.circle(cx, cy, r - 8, stroke=1, fill=0); c.setDash()
    initials = ''.join(w[0] for w in (name or 'S').split()[:3]).upper() or 'S'
    c.setFillColor(_GOLD); c.setFont('Times-Bold', 13)
    c.drawCentredString(cx, cy - 4, initials)
    c.setFont('Helvetica', 5); c.setFillColor(_GOLD_LT)
    c.drawCentredString(cx, cy + r - 10, 'OFFICIAL SEAL')


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
    if show.get('branch'):
        c.setFillColor(_MUTE); c.setFont('Times-Bold', 11)
        c.drawCentredString(cx, y, (ctx.get('branch') or 'Main Campus').upper()); y -= 16
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
    if show.get('branch'):
        c.setFillColor(MUTE); c.setFont('Times-Italic', 11); c.drawCentredString(cx, y, ctx.get('branch') or 'Main Campus'); y -= 14
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
    if show.get('branch'):
        c.setFillColor(colors.HexColor('#a5b4fc')); c.setFont('Helvetica', 11); c.drawString(48, ny, ctx.get('branch') or 'Main Campus')
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
    if show.get('branch'):
        c.setFillColor(MUTE); c.setFont('Helvetica', 10); c.drawString(mx0, my, ctx.get('branch') or 'Main Campus'); my -= 14
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
        my -= 14
    # signature / date / seal
    fy = max(56, my - 6)
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
    if show.get('school_stamp'):
        _seal(c, mx1 - 34, fy + 4, 24, ctx['school'].get('name'))
    if show.get('date_issued'):
        c.setFillColor(MUTE); c.setFont('Helvetica', 8.5); c.drawRightString(mx1, fy - 30, 'Issued ' + _issue_date().strftime('%d %b %Y'))


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
    if show.get('branch'):
        c.setFillColor(NAVY); c.setFont('Helvetica-Bold', 12.5); c.drawRightString(R, ry, ctx.get('branch') or 'Main Campus'); ry -= 18
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
        # Only stamp an *uploaded* signature image. With none, the space above the
        # line stays blank so the principal can sign the printed document by hand.
        sig = ctx['official'].get('signature_path') if show.get('principal_signature') else None
        if sig:
            try:
                c.drawImage(sig, M, line_y + 4, 108, 28, preserveAspectRatio=True, anchor='sw', mask='auto')
            except Exception:
                pass
        c.setStrokeColor(NAVY); c.setLineWidth(1.0); c.line(M, line_y, M + 165, line_y)
        pname = ctx['official'].get('principal_name') if show.get('principal_name') else None
        if pname:
            c.setFillColor(CHAR); c.setFont('Helvetica-Bold', 11); c.drawString(M, line_y - 15, pname.upper())
            c.setFillColor(MUTE); c.setFont('Helvetica', 9.5); c.drawString(M, line_y - 28, 'Principal')
        else:
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


# ===========================================================================
#  Design 8 — ACADEMIC PROFILE 2026 (minimalist institutional dossier, portrait)
#  A vertical identity rail (monogram, rotated WASSCE·year, photograph, faint
#  crest) sits beside a purely typographic academic record: a serif masthead, a
#  large student name, a numbered subject/grade list ruled with hairlines, a
#  whitespace stat summary and a restrained seal/QR authentication footer. It
#  leans on type, alignment and negative space rather than decoration, and every
#  zone reflows when a component is hidden.
# ===========================================================================
def _draw_profile(c, ctx, show, cfg, verify_url):
    from reportlab.lib.utils import ImageReader
    W, H = A4
    IVORY = colors.HexColor('#f4f1e7'); INK = colors.HexColor('#1a1a17')
    CHAR = colors.HexColor('#2e2e2a'); GREEN = colors.HexColor('#35503f')
    NUM = colors.HexColor('#c0baa8'); MUTE = colors.HexColor('#8f8b7f')
    HAIR = colors.HexColor('#d6d0c1'); FAINT = colors.HexColor('#e7e2d4')
    st = ctx['stats']
    logo = ctx['school'].get('logo_path') if show.get('school_logo') else None
    c.setFillColor(IVORY); c.rect(0, 0, W, H, fill=1, stroke=0)
    FM = 32
    RAIL_R = 172                     # x of the green identity-rail divider
    rcx = (FM + RAIL_R) / 2.0        # rail centre
    mx0, mx1 = RAIL_R + 28, W - FM   # main content column

    def _track(text, font, size, x, y, sp, color):
        c.setFillColor(color); c.setFont(font, size); xx = x
        for ch in text:
            c.drawString(xx, y, ch); xx += _sw(ch, font, size) + sp
        return xx - sp

    # ---- IDENTITY RAIL -----------------------------------------------------
    # Signature texture: fine vertical lines running the FULL rail height. The
    # monogram, photo and crest overprint them (each masked with the ivory ground
    # first), so the lines break cleanly around every element and continue below —
    # exactly as in the reference.
    photo_on = bool(show.get('student_photo') and ctx['student'].get('photo_path'))
    mono_y = H - 104
    pw, ph = 116, 132
    ph_x, ph_y = rcx - pw / 2.0, 440          # photo sits high in the rail
    c.setStrokeColor(colors.HexColor('#c3bca9')); c.setLineWidth(0.5)
    for i in range(12):
        xx = rcx - 33 + i * 6                 # centred in the rail
        c.line(xx, FM + 46, xx, H - 46)
    c.setStrokeColor(GREEN); c.setLineWidth(1.6); c.line(RAIL_R, FM + 30, RAIL_R, H - 30)
    if logo:
        c.setFillColor(IVORY); c.rect(rcx - 33, mono_y - 5, 66, 64, fill=1, stroke=0)   # break lines around monogram
        try:
            c.drawImage(logo, rcx - 27, mono_y, 54, 54, preserveAspectRatio=True, anchor='c', mask='auto')
        except Exception:
            pass
    if show.get('exam_name') or show.get('exam_year'):
        vy = 600
        c.setFillColor(IVORY); c.rect(rcx - 20, vy - 8, 60, 122, fill=1, stroke=0)   # break rails behind the label
        c.saveState(); c.translate(rcx - 10, vy); c.rotate(90)
        c.setFillColor(INK); c.setFont('Times-Bold', 23); c.drawString(0, 0, 'WASSCE'); c.restoreState()
        if show.get('exam_year'):
            c.saveState(); c.translate(rcx + 18, vy); c.rotate(90)
            c.setFillColor(GREEN); c.setFont('Times-Bold', 23); c.drawString(0, 0, str(ctx['exam']['year'])); c.restoreState()
    if photo_on:
        c.setFillColor(IVORY); c.rect(ph_x - 4, ph_y - 4, pw + 8, ph + 8, fill=1, stroke=0)   # clean break
        try:
            c.drawImage(ctx['student']['photo_path'], ph_x, ph_y, pw, ph, preserveAspectRatio=True, anchor='c', mask='auto')
        except Exception:
            c.setFillColor(colors.HexColor('#e5e7eb')); c.rect(ph_x, ph_y, pw, ph, fill=1, stroke=0)
        c.setStrokeColor(HAIR); c.setLineWidth(0.8); c.rect(ph_x, ph_y, pw, ph, stroke=1, fill=0)
    if logo:
        wm = _faded(logo, 0.06)
        if wm:
            try:
                c.drawImage(wm, rcx - 58, 96, 116, 116, preserveAspectRatio=True, anchor='c', mask='auto')
            except Exception:
                pass

    # ---- MAIN · header -----------------------------------------------------
    y = H - 58
    if show.get('school_name') and ctx['school'].get('name'):
        c.setFillColor(INK); c.setFont('Times-Bold', 22); c.drawString(mx0, y, ctx['school']['name'].upper()); y -= 17
    if show.get('exam_name'):
        _track('WEST AFRICAN SENIOR SCHOOL CERTIFICATE EXAMINATION', 'Helvetica-Bold', 10.5, mx0, y, 0.4, MUTE); y -= 27
    if show.get('exam_year'):
        c.setFillColor(GREEN); c.setFont('Times-Bold', 23); c.drawString(mx0, y, str(ctx['exam']['year'])); y -= 14

    # ---- MAIN · student identity ------------------------------------------
    y -= 22
    last = y
    if show.get('student_name'):
        for ln in _wrap(c, ctx['student']['name'].upper(), 'Times-Bold', 34, mx1 - mx0)[:2]:
            c.setFillColor(INK); c.setFont('Times-Bold', 34); c.drawString(mx0, y, ln); last = y; y -= 37
    meta = []
    if show.get('candidate_no') and ctx['student'].get('candidate_no'):
        meta.append((cfg.get('candidate_label') or 'CANDIDATE NO.') + ' ' + str(ctx['student']['candidate_no']))
    if show.get('admission_no') and ctx['student'].get('admission_no'):
        meta.append('ADM. ' + str(ctx['student']['admission_no']))
    if show.get('exam_number') and ctx['student'].get('exam_number'):
        meta.append('EXAM NO. ' + str(ctx['student']['exam_number']))
    if show.get('student_class') and ctx['student'].get('klass'):
        meta.append('CLASS ' + str(ctx['student']['klass']))
    if meta:
        y = last - 24                       # candidate sits close under the name
        _track('     '.join(meta), 'Helvetica-Bold', 11.5, mx0, y, 0.5, MUTE)
    rows_top = y - 30

    # ---- bottom-anchored zones --------------------------------------------
    foot_rule_y = FM + 38
    stats = []
    if show.get('total_subjects'): stats.append((st['total'], 'SUBJECTS'))
    if show.get('a1_count'):       stats.append((st['a1'], 'A1'))
    if show.get('credits'):        stats.append((st['credits'], 'CREDITS'))
    if show.get('average'):        stats.append((st['average'], 'AVERAGE'))
    if show.get('classification'): stats.append((st['classification'], 'CLASS'))
    off_top = foot_rule_y + 168
    sum_num_y = (off_top + 40) if stats else off_top
    results_bottom = (sum_num_y + 40) if stats else (off_top + 16)

    # ---- MAIN · academic record (numbered list) ---------------------------
    results = ctx['results']
    n = len(results)
    if show.get('subjects') and n:
        avail = rows_top - results_bottom
        rh = min(36, max(20, avail / n))
        subj_fs = 15 if rh >= 28 else 13
        num_fs = 20 if rh >= 28 else 16
        yy = rows_top
        for i, r in enumerate(results, 1):
            base = yy - rh * 0.60
            c.setFillColor(NUM); c.setFont('Times-Roman', num_fs); c.drawString(mx0, base, f'{i:02d}')
            sx = mx0 + num_fs + 20
            c.setFillColor(INK); c.setFont('Helvetica-Bold', subj_fs)
            c.drawString(sx, base, r['subject'].upper())
            subj_end = sx + _sw(r['subject'].upper(), 'Helvetica-Bold', subj_fs)
            gtxt = r['grade'] if show.get('grades') else ''
            gx = mx1
            if gtxt:
                c.setFillColor(INK); c.setFont('Times-Bold', subj_fs + 3); c.drawRightString(mx1, base, gtxt)
                gx = mx1 - _sw(gtxt, 'Times-Bold', subj_fs + 3)
            if show.get('grade_desc') and r.get('desc'):
                c.setFillColor(MUTE); c.setFont('Helvetica', subj_fs - 6); c.drawString(subj_end + 10, base, r['desc'])
                subj_end += _sw('  ' + r['desc'], 'Helvetica', subj_fs - 6)
            if gtxt and gx - (subj_end + 16) > 24:               # connecting leader rule
                c.setStrokeColor(HAIR); c.setLineWidth(0.8); c.line(subj_end + 14, base + 4, gx - 14, base + 4)
            c.setStrokeColor(HAIR); c.setLineWidth(0.7); c.line(mx0, yy - rh, mx1, yy - rh)
            yy -= rh

    # ---- MAIN · minimalist summary (evenly justified: left · centre · right) --
    if stats:
        ns = len(stats)
        for i, (v, l) in enumerate(stats):
            if i == 0:
                x, draw = mx0, c.drawString
            elif i == ns - 1:
                x, draw = mx1, c.drawRightString
            else:
                x, draw = mx0 + (mx1 - mx0) * i / (ns - 1), c.drawCentredString
            txt = f'{v:02d}' if isinstance(v, int) else str(v)
            c.setFillColor(INK); c.setFont('Times-Bold', 38); draw(x, sum_num_y, txt)
            c.setFillColor(MUTE); c.setFont('Helvetica-Bold', 10.5); draw(x, sum_num_y - 19, l)

    # ---- MAIN · official authentication -----------------------------------
    #  A single balanced row: signature (left) · seal (centre) · QR + code (right),
    #  their tops aligned so they read as one band, as in the reference.
    oy = off_top - 6
    if show.get('principal_signature') or show.get('principal_name'):
        line_y = oy - 44
        c.setFillColor(MUTE); c.setFont('Helvetica-Bold', 8.5); c.drawString(mx0, oy, 'PRINCIPAL SIGNATURE')
        sig = ctx['official'].get('signature_path') if show.get('principal_signature') else None
        if sig:
            try:
                c.drawImage(sig, mx0, line_y + 4, 120, 30, preserveAspectRatio=True, anchor='sw', mask='auto')
            except Exception:
                pass
        c.setStrokeColor(INK); c.setLineWidth(0.9); c.line(mx0, line_y, mx0 + 140, line_y)
        pname = ctx['official'].get('principal_name') if show.get('principal_name') else None
        if pname:
            c.setFillColor(INK); c.setFont('Times-Bold', 12.5); c.drawString(mx0, line_y - 17, pname)
        c.setFillColor(MUTE); c.setFont('Helvetica', 8.5); c.drawString(mx0, line_y - 29, 'Principal Name')
        if show.get('date_issued'):
            c.setFillColor(MUTE); c.setFont('Helvetica-Bold', 8)
            c.drawString(mx0, line_y - 46, 'DATE ISSUED: ' + _issue_date().strftime('%B %Y').upper())
    if show.get('school_stamp'):
        _seal(c, (mx0 + mx1) / 2.0, oy - 42, 40, ctx['school'].get('name'))
    if show.get('qr_code') or show.get('verification_code'):
        qr = 62
        if show.get('qr_code') and verify_url:
            try:
                import qrcode
                qb = io.BytesIO(); qrcode.make(verify_url).save(qb, format='PNG'); qb.seek(0)
                c.drawImage(ImageReader(qb), mx1 - qr, oy - qr + 4, qr, qr, mask='auto')
            except Exception:
                pass
        if show.get('verification_code') and ctx.get('verify_code'):
            code = str(ctx['verify_code']); fs = 10.0
            while _sw(code, 'Helvetica-Bold', fs) > (mx1 - mx0) and fs > 6:
                fs -= 0.5
            c.setFillColor(INK); c.setFont('Helvetica-Bold', fs); c.drawRightString(mx1, oy - qr - 12, code)
            c.setFillColor(MUTE); c.setFont('Helvetica', 8.5); c.drawRightString(mx1, oy - qr - 24, 'Verification Code')

    # ---- FOOTER (spans the full width) ------------------------------------
    c.setStrokeColor(HAIR); c.setLineWidth(0.8); c.line(FM, foot_rule_y, W - FM, foot_rule_y)
    left = ctx['school'].get('name', '') or ''
    if show.get('school_address') and ctx['school'].get('address'):
        left = (left + ' · ' + ctx['school']['address']).strip(' ·')
    if show.get('footer_custom') and cfg.get('footer_text'):
        left = cfg['footer_text']
    right = []
    if show.get('footer_contact') and ctx['school'].get('phone'):
        right.append(ctx['school']['phone'])
    if show.get('footer_website') and ctx['school'].get('website'):
        right.append(ctx['school']['website'])
    c.setFont('Helvetica', 8.5); c.setFillColor(CHAR)
    if left:
        c.drawString(FM, foot_rule_y - 16, left)
    if right:
        c.drawRightString(W - FM, foot_rule_y - 16, ' · '.join(right))


# ===========================================================================
#  Design 9 — MERIDIAN 2026 (contemporary institutional, architectural geometry)
#  An angular layered WASSCE·year badge, a bevel-framed portrait, a large central
#  result panel with numbered rows + bold grades inside a layered navy/green
#  frame, a green stat bar with a cut corner, and a framed seal/QR verification
#  row. Asymmetric, geometric and expressive — distinct from the other layouts.
# ===========================================================================
def _draw_meridian(c, ctx, show, cfg, verify_url):
    from reportlab.lib.utils import ImageReader
    W, H = A4
    IVORY = colors.HexColor('#f4f1e6'); INK = colors.HexColor('#1f1e1b')
    GREEN = colors.HexColor('#33523f'); NAVY = colors.HexColor('#27374f')
    RUST = colors.HexColor('#9c6a4a'); MUTE = colors.HexColor('#8a8578')
    HAIR = colors.HexColor('#d5cfbe'); WHITE = colors.white
    st = ctx['stats']
    logo = ctx['school'].get('logo_path') if show.get('school_logo') else None
    FM = 26; R = W - FM

    def bpath(x, y, w, h, cut):
        p = c.beginPath()
        p.moveTo(x, y + cut); p.lineTo(x, y + h); p.lineTo(x + w - cut, y + h)
        p.lineTo(x + w, y + h - cut); p.lineTo(x + w, y); p.lineTo(x + cut, y); p.close()
        return p

    def bev(x, y, w, h, cut, fill=None, stroke=None, sw=1):
        c.drawPath(bpath(x, y, w, h, cut),
                   fill=1 if fill else 0, stroke=1 if stroke else 0) if False else None
        if fill is not None:
            c.setFillColor(fill)
        if stroke is not None:
            c.setStrokeColor(stroke); c.setLineWidth(sw)
        c.drawPath(bpath(x, y, w, h, cut), fill=1 if fill is not None else 0,
                   stroke=1 if stroke is not None else 0)

    def frame(x, y, w, h, cut):                      # layered architectural frame
        bev(x + 7, y - 7, w, h, cut, fill=NAVY)
        bev(x - 7, y + 7, w, h, cut, fill=GREEN)
        bev(x, y, w, h, cut, fill=IVORY, stroke=INK, sw=0.8)

    def tlbr_path(x, y, w, h, cut):                  # cut top-left + bottom-right corners
        p = c.beginPath()
        p.moveTo(x, y); p.lineTo(x, y + h - cut); p.lineTo(x + cut, y + h)
        p.lineTo(x + w, y + h); p.lineTo(x + w, y + cut); p.lineTo(x + w - cut, y); p.close()
        return p

    def arrow_path(x, y, w, h, pt, bl=0):            # right-pointing arrow, optional bottom-left cut
        p = c.beginPath()
        p.moveTo(x + bl, y); p.lineTo(x, y + bl); p.lineTo(x, y + h)
        p.lineTo(x + w - pt, y + h); p.lineTo(x + w, y + h / 2.0)
        p.lineTo(x + w - pt, y); p.close()
        return p

    c.setFillColor(IVORY); c.rect(0, 0, W, H, fill=1, stroke=0)
    # faint architectural diagonals (top-right)
    c.setStrokeColor(HAIR); c.setLineWidth(0.6)
    for i in range(4):
        c.line(R - 150 + i * 12, H - 30, R - 30 + i * 12, H - 150)

    # ---- top-right · school identity --------------------------------------
    #  School name is right-aligned; the logo is placed to the LEFT of the actual
    #  (widest) name line with a gap, so it never overlaps the text, and the
    #  branch/motto reflow beneath whatever the name occupies.
    nm_r = R
    name_lines = _wrap(c, ctx['school']['name'].upper(), 'Times-Bold', 20, 188)[:2] \
        if (show.get('school_name') and ctx['school'].get('name')) else []
    name_w = max((_sw(ln, 'Times-Bold', 20) for ln in name_lines), default=0)
    yy = H - 50
    for ln in name_lines:
        c.setFillColor(INK); c.setFont('Times-Bold', 20); c.drawRightString(nm_r, yy, ln); yy -= 22
    if logo:
        try:
            block_h = 22 * max(len(name_lines), 1)
            ly = (H - 44) - block_h / 2 - 22          # centred on the name block
            lx = nm_r - name_w - 14 - 46              # 14px gap before the name
            c.drawImage(logo, lx, ly, 46, 46, preserveAspectRatio=True, anchor='c', mask='auto')
        except Exception:
            pass
    ry = (H - 50) - 22 * max(len(name_lines), 1) - 12
    if show.get('branch'):
        c.setFillColor(INK); c.setFont('Helvetica-Bold', 10); c.drawRightString(R, ry, (ctx.get('branch') or 'Main Campus').upper()); ry -= 13
    if show.get('school_motto') and ctx['school'].get('motto'):
        c.setFillColor(MUTE); c.setFont('Helvetica-Oblique', 9); c.drawRightString(R, ry, ctx['school']['motto'])

    # ---- top-left · WASSCE·year ARROW badge -------------------------------
    #  One layered right-pointing arrow: rust accent (back-left) + navy shadow +
    #  green arrow, with a cream card (right-pointed, bottom-left cut) carrying
    #  the exam title + WASSCE on the left, and 2026 sitting on the green head.
    bx, by, bh = FM + 6, H - 176, 96
    cw, gw, tip = 250, 96, 32
    total = cw + gw
    c.setFillColor(RUST); c.rect(bx - 8, by + 8, 96, bh, fill=1, stroke=0)              # rust accent (top-left peek)
    c.setFillColor(NAVY); c.drawPath(arrow_path(bx + 8, by - 8, total, bh, tip), fill=1, stroke=0)   # navy shadow
    c.setFillColor(GREEN); c.drawPath(arrow_path(bx, by, total, bh, tip), fill=1, stroke=0)          # green arrow
    c.setFillColor(IVORY); c.setStrokeColor(INK); c.setLineWidth(0.9)                    # cream card (right-pointed)
    c.drawPath(arrow_path(bx + 4, by + 5, cw, bh - 10, 24, bl=14), fill=1, stroke=1)
    if show.get('exam_name'):
        for i, ln in enumerate(_wrap(c, 'WEST AFRICAN SENIOR SCHOOL CERTIFICATE EXAMINATION',
                                     'Helvetica-Bold', 9, cw - 60)[:2]):
            c.setFillColor(INK); c.setFont('Helvetica-Bold', 9); c.drawString(bx + 16, by + bh - 22 - i * 11, ln)
    c.setFillColor(INK); c.setFont('Helvetica-Bold', 42); c.drawString(bx + 14, by + 16, 'WASSCE')
    if show.get('exam_year'):
        c.setFillColor(WHITE); c.setFont('Helvetica-Bold', 22)
        c.drawCentredString(bx + cw + (gw - tip) / 2.0, by + bh / 2 - 8, str(ctx['exam']['year']))

    # ---- student identity (left) ------------------------------------------
    ny = H - 224
    if show.get('student_name'):
        for ln in _wrap(c, ctx['student']['name'].upper(), 'Helvetica-Bold', 33, 380)[:2]:
            c.setFillColor(INK); c.setFont('Helvetica-Bold', 33); c.drawString(FM, ny, ln); ny -= 35
    meta = []
    if show.get('candidate_no') and ctx['student'].get('candidate_no'):
        meta.append((cfg.get('candidate_label') or 'CANDIDATE NO.') + ' ' + str(ctx['student']['candidate_no']))
    if show.get('exam_number') and ctx['student'].get('exam_number'):
        meta.append('EXAM NO. ' + str(ctx['student']['exam_number']))
    if show.get('admission_no') and ctx['student'].get('admission_no'):
        meta.append('ADM. ' + str(ctx['student']['admission_no']))
    if show.get('student_class') and ctx['student'].get('klass'):
        meta.append('CLASS ' + str(ctx['student']['klass']))
    if meta:
        c.setFillColor(INK); c.setFont('Helvetica-Bold', 11); c.drawString(FM, ny - 4, '   ·   '.join(meta))

    # ---- portrait in an angular green frame (right) -----------------------
    #  Cut top-left + bottom-right corners (parallelogram feel), green frame on a
    #  navy shadow, with fine diagonal accents above-left.
    if show.get('student_photo') and ctx['student'].get('photo_path'):
        fw, fh = 138, 156; fx = R - fw; fy = H - 304
        c.setStrokeColor(HAIR); c.setLineWidth(0.6)
        for i in range(4):
            c.line(fx - 40 + i * 10, fy + fh, fx - 6 + i * 10, fy + fh - 34)
        c.setFillColor(NAVY); c.drawPath(tlbr_path(fx + 6, fy - 6, fw, fh, 22), fill=1, stroke=0)
        c.setFillColor(GREEN); c.drawPath(tlbr_path(fx, fy, fw, fh, 22), fill=1, stroke=0)
        ix, iy, iw, ih = fx + 9, fy + 9, fw - 18, fh - 18
        c.saveState(); c.clipPath(tlbr_path(ix, iy, iw, ih, 17), stroke=0, fill=0)
        try:
            c.drawImage(ctx['student']['photo_path'], ix, iy, iw, ih, preserveAspectRatio=True, anchor='c', mask='auto')
        except Exception:
            c.setFillColor(colors.HexColor('#dfe3e8')); c.rect(ix, iy, iw, ih, fill=1, stroke=0)
        c.restoreState()

    # ---- bottom-anchored zones --------------------------------------------
    foot_y = FM + 6
    stats = []
    if show.get('total_subjects'): stats.append((st['total'], 'SUBJECTS'))
    if show.get('a1_count'):       stats.append((st['a1'], 'A1'))
    if show.get('credits'):        stats.append((st['credits'], 'CREDITS'))
    if show.get('average'):        stats.append((st['average'], 'AVERAGE'))
    if show.get('classification'): stats.append((st['classification'], 'CLASS'))
    ver_h = 122; ver_y = foot_y + 24
    sum_h = 48 if stats else 0
    sum_y = ver_y + ver_h + 16            # green summary strip base = combined-panel base
    panel_top = H - 306

    # ---- result panel + summary (ONE blended unit) ------------------------
    in_x, in_w = FM + 7, (R - FM) - 14
    frame(in_x, sum_y, in_w, panel_top - sum_y, 22)
    if stats:                              # green summary strip flush at the panel's base
        c.saveState(); c.clipPath(bpath(in_x, sum_y, in_w, panel_top - sum_y, 22), stroke=0, fill=0)
        c.setFillColor(GREEN); c.rect(in_x, sum_y, in_w, sum_h, fill=1, stroke=0)
        c.restoreState()
        c.setStrokeColor(colors.HexColor('#c8c2b1')); c.setLineWidth(0.8)
        c.line(in_x + 16, sum_y + sum_h, in_x + in_w - 16, sum_y + sum_h)
    ip_x0, ip_x1 = FM + 26, R - 26
    rows_top = panel_top - 26
    rows_bot = sum_y + sum_h + 16
    results = ctx['results']; n = len(results)
    if show.get('subjects') and n:
        rh = min(34, max(16, (rows_top - rows_bot) / n))
        subj_fs = 16 if rh >= 24 else (14 if rh >= 20 else 12)
        grade_fs = subj_fs + 9 if rh >= 26 else subj_fs + 6
        yy = rows_top
        for i, r in enumerate(results, 1):
            base = yy - rh * 0.60
            c.setFillColor(MUTE); c.setFont('Helvetica-Bold', subj_fs - 5); c.drawString(ip_x0, base, f'{i:02d}')
            c.setFillColor(INK); c.setFont('Helvetica-Bold', subj_fs)
            c.drawString(ip_x0 + 34, base, r['subject'].upper())
            if show.get('grades'):
                c.setFillColor(INK); c.setFont('Helvetica-Bold', grade_fs); c.drawRightString(ip_x1, base, r['grade'])
            if i < n:
                c.setStrokeColor(HAIR); c.setLineWidth(0.7); c.line(ip_x0, yy - rh, ip_x1, yy - rh)
            yy -= rh
    if stats:                              # summary values over the green strip
        ns = len(stats); seg = in_w / ns
        for i, (v, l) in enumerate(stats):
            sxc = in_x + seg * i + seg / 2
            txt = f'{v:02d}' if isinstance(v, int) else str(v)
            c.setFillColor(WHITE); c.setFont('Helvetica-Bold', 25); c.drawCentredString(sxc, sum_y + 18, txt)
            c.setFillColor(colors.HexColor('#c9d6cd')); c.setFont('Helvetica-Bold', 8.5); c.drawCentredString(sxc, sum_y + 7, l)
            if i:
                c.setStrokeColor(colors.HexColor('#4a6a55')); c.setLineWidth(0.8)
                c.line(in_x + seg * i, sum_y + 8, in_x + seg * i, sum_y + sum_h - 8)

    # ---- verification / signature row -------------------------------------
    frame(in_x, ver_y, in_w, ver_h, 18)
    vx0, vx1 = FM + 26, R - 26
    vtop = ver_y + ver_h
    # QR (right, larger)
    qs = 76; qx = vx1 - qs; qy = vtop - 16 - qs
    if show.get('qr_code') and verify_url:
        try:
            import qrcode
            qb = io.BytesIO(); qrcode.make(verify_url).save(qb, format='PNG'); qb.seek(0)
            c.drawImage(ImageReader(qb), qx, qy, qs, qs, mask='auto')
        except Exception:
            pass
    # verification code — in the space BEFORE the QR
    vc_r = qx - 18
    if show.get('verification_code') and ctx.get('verify_code'):
        code = str(ctx['verify_code']); fs = 11.0
        while _sw(code, 'Helvetica-Bold', fs) > 158 and fs > 7:
            fs -= 0.5
        c.setFillColor(MUTE); c.setFont('Helvetica-Bold', 8); c.drawRightString(vc_r, vtop - 40, 'VERIFICATION CODE')
        c.setFillColor(INK); c.setFont('Helvetica-Bold', fs); c.drawRightString(vc_r, vtop - 56, code)
    if show.get('date_issued'):
        c.setFillColor(MUTE); c.setFont('Helvetica', 8); c.drawRightString(vx1, qy - 12, 'Issued ' + _issue_date().strftime('%d %b %Y'))
    # seal (centre-left)
    if show.get('school_stamp'):
        _seal(c, vx0 + 205, ver_y + ver_h / 2, 34, ctx['school'].get('name'))
    # signature (left)
    if show.get('principal_signature') or show.get('principal_name'):
        line_y = ver_y + 46
        sig = ctx['official'].get('signature_path') if show.get('principal_signature') else None
        if sig:
            try:
                c.drawImage(sig, vx0, line_y + 4, 110, 26, preserveAspectRatio=True, anchor='sw', mask='auto')
            except Exception:
                pass
        else:
            c.setFillColor(INK); c.setFont('Times-Italic', 20); c.drawString(vx0, line_y + 6, 'Principal')
        c.setStrokeColor(INK); c.setLineWidth(0.8); c.line(vx0, line_y, vx0 + 150, line_y)
        c.setFillColor(MUTE); c.setFont('Helvetica-Bold', 8); c.drawString(vx0, line_y - 13, 'PRINCIPAL NAME')
        pname = ctx['official'].get('principal_name') if show.get('principal_name') else None
        if pname:
            c.setFillColor(INK); c.setFont('Helvetica-Bold', 10); c.drawString(vx0, line_y - 26, pname)

    # ---- footer -----------------------------------------------------------
    parts = []
    nm = ctx['school'].get('name', '') or ''
    if show.get('school_address') and ctx['school'].get('address'):
        nm = (nm + ' · ' + ctx['school']['address']).strip(' ·')
    if nm:
        parts.append(nm)
    if show.get('footer_contact') and ctx['school'].get('phone'):
        parts.append(ctx['school']['phone'])
    if show.get('footer_website') and ctx['school'].get('website'):
        parts.append(ctx['school']['website'])
    if show.get('footer_custom') and cfg.get('footer_text'):
        parts = [cfg['footer_text']]
    if parts:
        c.setStrokeColor(HAIR); c.setLineWidth(0.7); c.line(FM, foot_y + 14, R, foot_y + 14)
        c.setFillColor(MUTE); c.setFont('Helvetica', 8.5)
        c.drawCentredString(W / 2, foot_y, '   |   '.join(parts))


# ===========================================================================
#  Design 10 — AURELIS 2026 (editorial serif publication, portrait)
#  A right-aligned crest masthead, a ruled WASSCE·year band, an oversized
#  multi-line student name beside a crop-marked portrait, a two-column bordered
#  subject/grade matrix over a faint crest watermark, a centred achievement line,
#  and a signature/seal/QR verification block above a three-column label row.
#  Serif-led, monochromatic and typographic — distinct from the other designs.
# ===========================================================================
def _draw_aurelis(c, ctx, show, cfg, verify_url):
    from reportlab.lib.utils import ImageReader
    W, H = A4
    IVORY = colors.HexColor('#f3f0e7'); NAVY = colors.HexColor('#22334a')
    INK = colors.HexColor('#1f1f1c'); GRAY = colors.HexColor('#7c7c72')
    HAIR = colors.HexColor('#cfc9ba')
    st = ctx['stats']
    logo = ctx['school'].get('logo_path') if show.get('school_logo') else None
    FM = 42; R = W - FM
    c.setFillColor(IVORY); c.rect(0, 0, W, H, fill=1, stroke=0)

    def track(text, font, size, x, y, sp, color, right=False):
        c.setFillColor(color); c.setFont(font, size)
        total = sum(_sw(ch, font, size) + sp for ch in text) - (sp if text else 0)
        xx = (x - total) if right else x
        for ch in text:
            c.drawString(xx, y, ch); xx += _sw(ch, font, size) + sp

    # 1 · school identity (top-right: name then crest) ----------------------
    if logo:
        try:
            c.drawImage(logo, R - 42, H - 78, 42, 42, preserveAspectRatio=True, anchor='c', mask='auto')
        except Exception:
            pass
    nm_r = R - (52 if logo else 0)
    yy = H - 58
    for ln in (_wrap(c, ctx['school']['name'].upper(), 'Times-Bold', 18, 230)[:2]
               if (show.get('school_name') and ctx['school'].get('name')) else []):
        c.setFillColor(NAVY); c.setFont('Times-Bold', 18); c.drawRightString(nm_r, yy, ln); yy -= 20

    # 2 · examination line (left) + branch/motto (right) --------------------
    if show.get('exam_name'):
        track('WEST AFRICAN SENIOR SCHOOL', 'Helvetica-Bold', 9, FM, H - 100, 0.4, GRAY)
        track('CERTIFICATE EXAMINATION', 'Helvetica-Bold', 9, FM, H - 112, 0.4, GRAY)
    ry = H - 98
    if show.get('branch'):
        c.setFillColor(INK); c.setFont('Helvetica', 12); c.drawRightString(R, ry, ctx.get('branch') or 'Main Campus'); ry -= 15
    if show.get('school_motto') and ctx['school'].get('motto'):
        c.setFillColor(GRAY); c.setFont('Helvetica-Oblique', 9.5); c.drawRightString(R, ry, ctx['school']['motto'])
    c.setStrokeColor(HAIR); c.setLineWidth(0.9); c.line(FM, H - 128, R, H - 128)

    # 3 · WASSCE · year band ------------------------------------------------
    c.setFillColor(NAVY); c.setFont('Times-Bold', 46); c.drawString(FM, H - 176, 'WASSCE')
    if show.get('exam_year'):
        c.setFillColor(GRAY); c.setFont('Times-Bold', 46); c.drawRightString(R, H - 176, str(ctx['exam']['year']))
    c.setStrokeColor(HAIR); c.setLineWidth(0.9); c.line(FM, H - 194, R, H - 194)

    # 4 · student identity + crop-marked portrait ---------------------------
    photo_on = bool(show.get('student_photo') and ctx['student'].get('photo_path'))
    pw, ph = 156, 176; px = R - pw; py = H - 392
    name_w = (px - 26 - FM) if photo_on else (R - FM)
    ny = H - 234
    if show.get('student_name'):
        for ln in _wrap(c, ctx['student']['name'].upper(), 'Times-Bold', 44, name_w)[:3]:
            c.setFillColor(INK); c.setFont('Times-Bold', 44); c.drawString(FM, ny, ln); ny -= 44
    if show.get('candidate_no') and ctx['student'].get('candidate_no'):
        c.setFillColor(INK); c.setFont('Helvetica', 13)
        c.drawString(FM, ny + 4, (cfg.get('candidate_label') or 'Candidate Number:') + ' ' + str(ctx['student']['candidate_no']))
    if photo_on:
        try:
            c.drawImage(ctx['student']['photo_path'], px, py, pw, ph, preserveAspectRatio=True, anchor='c', mask='auto')
        except Exception:
            c.setFillColor(colors.HexColor('#dfe3e8')); c.rect(px, py, pw, ph, fill=1, stroke=0)
        c.setStrokeColor(NAVY); c.setLineWidth(0.9); m, ln = 7, 17     # corner crop marks
        for cx0, cy0, sx, sy2 in ((px, py + ph, 1, -1), (px + pw, py + ph, -1, -1),
                                  (px, py, 1, 1), (px + pw, py, -1, 1)):
            c.line(cx0 - sx * m, cy0 + sy2 * m, cx0 - sx * m + sx * ln, cy0 + sy2 * m)
            c.line(cx0 - sx * m, cy0 + sy2 * m, cx0 - sx * m, cy0 + sy2 * m - sy2 * ln)

    # ---- bottom-anchored zones --------------------------------------------
    foot_y = FM - 2
    stats = []
    if show.get('total_subjects'): stats.append((st['total'], 'SUBJECTS'))
    if show.get('a1_count'):       stats.append((st['a1'], 'A1'))
    if show.get('credits'):        stats.append((st['credits'], 'CREDITS'))
    if show.get('average'):        stats.append((st['average'], 'AVERAGE'))
    if show.get('classification'): stats.append((st['classification'], 'CLASS'))
    ver_bottom = foot_y + 34
    ver_top = ver_bottom + 140
    sum_y = (ver_top + 24) if stats else ver_top
    box_bot = sum_y + (20 if stats else 8)

    # 5 · results — two-column bordered matrix ------------------------------
    box_top = H - 410
    bx0, bx1 = FM, R
    c.setStrokeColor(HAIR); c.setLineWidth(0.9)
    c.rect(bx0, box_bot, bx1 - bx0, box_top - box_bot, stroke=1, fill=0)
    midx = (bx0 + bx1) / 2.0
    c.line(midx, box_bot + 12, midx, box_top - 12)
    if logo:                                                   # faint crest watermark
        wm = _faded(logo, 0.05)
        if wm:
            try:
                c.drawImage(wm, midx - 70, (box_top + box_bot) / 2 - 70, 140, 140,
                            preserveAspectRatio=True, anchor='c', mask='auto')
            except Exception:
                pass
    results = ctx['results']; n = len(results)
    if show.get('subjects') and n:
        half = (n + 1) // 2
        cols = [(results[:half], bx0 + 24, midx - 22), (results[half:], midx + 24, bx1 - 22)]
        rh = min(38, max(18, (box_top - box_bot - 24) / max(half, 1)))
        subj_fs = 16 if rh >= 24 else 13
        for items, x0, x1 in cols:
            y = box_top - 20
            for r in items:
                base = y - rh * 0.55
                c.setFillColor(INK); c.setFont('Times-Roman', subj_fs); c.drawString(x0, base, r['subject'])
                if show.get('grades'):
                    g = r['grade']; c.setFont('Times-Bold', subj_fs + 5)
                    gw = _sw(g, 'Times-Bold', subj_fs + 5); gx = x1 - gw
                    c.setFillColor(GRAY); c.setFont('Times-Roman', subj_fs); c.drawString(gx - 20, base, '—')
                    c.setFillColor(INK); c.setFont('Times-Bold', subj_fs + 5); c.drawString(gx, base, g)
                y -= rh

    # 6 · achievement line (centred) ----------------------------------------
    if stats:
        segw = [(_sw(f'{v:02d}' if isinstance(v, int) else str(v), 'Times-Bold', 22) + 6
                 + _sw(l, 'Times-Roman', 19)) for v, l in stats]
        sepw = _sw('   |   ', 'Times-Roman', 19)
        xx = (W - (sum(segw) + sepw * (len(stats) - 1))) / 2.0
        for i, (v, l) in enumerate(stats):
            txt = f'{v:02d}' if isinstance(v, int) else str(v)
            c.setFillColor(NAVY); c.setFont('Times-Bold', 22); c.drawString(xx, sum_y, txt); xx += _sw(txt, 'Times-Bold', 22) + 6
            c.setFillColor(INK); c.setFont('Times-Roman', 19); c.drawString(xx, sum_y, l); xx += _sw(l, 'Times-Roman', 19)
            if i < len(stats) - 1:
                c.setFillColor(GRAY); c.setFont('Times-Roman', 19); c.drawString(xx, sum_y, '   |   '); xx += sepw

    # 7 · verification -------------------------------------------------------
    #  Row A: signature (left) · seal (centre) · QR (right).
    rowA = ver_top - 34
    if show.get('principal_signature') or show.get('principal_name'):
        sig = ctx['official'].get('signature_path') if show.get('principal_signature') else None
        if sig:
            try:
                c.drawImage(sig, FM, rowA - 4, 130, 30, preserveAspectRatio=True, anchor='sw', mask='auto')
            except Exception:
                sig = None
        if not sig:
            c.setFillColor(INK); c.setFont('Times-Italic', 19); c.drawString(FM, rowA, 'Signature')
        c.setStrokeColor(HAIR); c.setLineWidth(0.8); c.line(FM, rowA - 8, FM + 165, rowA - 8)
        track('PRINCIPAL SIGNATURE', 'Helvetica-Bold', 8, FM, rowA - 22, 0.5, GRAY)
    if show.get('school_stamp'):
        _seal(c, W / 2, rowA + 2, 31, ctx['school'].get('name'))
    if show.get('qr_code') and verify_url:
        try:
            import qrcode
            qb = io.BytesIO(); qrcode.make(verify_url).save(qb, format='PNG'); qb.seek(0)
            c.drawImage(ImageReader(qb), R - 62, rowA - 30, 62, 62, mask='auto')
        except Exception:
            pass
    #  Row B: three label/value columns.
    rowB = ver_bottom + 28
    def field(label, value, x, align='l'):
        draw = c.drawRightString if align == 'r' else (c.drawCentredString if align == 'c' else c.drawString)
        if align == 'r':
            track(label, 'Helvetica-Bold', 7.5, x, rowB, 0.5, GRAY, right=True)
        elif align == 'c':
            c.setFillColor(GRAY); c.setFont('Helvetica-Bold', 7.5); c.drawCentredString(x, rowB, label)
        else:
            track(label, 'Helvetica-Bold', 7.5, x, rowB, 0.5, GRAY)
        c.setFillColor(INK); c.setFont('Helvetica', 11); draw(x, rowB - 14, value)
    pn = ctx['official'].get('principal_name') if show.get('principal_name') else None
    if pn:
        field("PRINCIPAL'S NAME", pn, FM, 'l')
    if show.get('verification_code') and ctx.get('verify_code'):
        field('VERIFICATION NUMBER', str(ctx['verify_code']), W / 2, 'c')
    if show.get('date_issued'):
        field('DATE ISSUED', _issue_date().strftime('%d/%m/%Y'), R, 'r')

    # 8 · footer ------------------------------------------------------------
    parts = []
    nm = ctx['school'].get('name', '') or ''
    if show.get('school_address') and ctx['school'].get('address'):
        nm = (nm + ' · ' + ctx['school']['address']).strip(' ·')
    if nm:
        parts.append(nm)
    if show.get('footer_contact') and ctx['school'].get('phone'):
        parts.append(ctx['school']['phone'])
    if show.get('footer_website') and ctx['school'].get('website'):
        parts.append(ctx['school']['website'])
    if show.get('footer_custom') and cfg.get('footer_text'):
        parts = [cfg['footer_text']]
    if parts:
        c.setStrokeColor(HAIR); c.setLineWidth(0.8); c.line(FM, foot_y + 16, R, foot_y + 16)
        c.setFillColor(GRAY); c.setFont('Helvetica', 8.5); c.drawCentredString(W / 2, foot_y, '   ·   '.join(parts))


# ===========================================================================
#  Design 11 — MONUMENT 2026 (premium institutional annual-report, portrait)
#  An asymmetric editorial masthead (crest + school name left, WASSCE·year
#  right, joined by a fine gold rule), a vertical WASSCE marker down the left
#  margin, a compact examination label, an oversized serif student name beside
#  a rectangular portrait, a three-column NUMBER/SUBJECT/GRADE record with
#  banded rows and strong grade typography, an editorial stat line, and a
#  restrained signature / teal seal / verification+QR authentication row.
# ===========================================================================
def _draw_monument(c, ctx, show, cfg, verify_url):
    import math
    from reportlab.lib.utils import ImageReader
    W, H = A4
    NAVY = colors.HexColor('#14213D'); TEAL = colors.HexColor('#1F5C5B')
    GOLD = colors.HexColor('#C5A46D'); IVORY = colors.HexColor('#F7F4ED')
    CHAR = colors.HexColor('#252525'); GRAY = colors.HexColor('#6B6B6B')
    HAIR = colors.HexColor('#dcd6c7'); BAND = colors.HexColor('#efeadd')
    FM = 44; R = W - FM
    c.setFillColor(IVORY); c.rect(0, 0, W, H, fill=1, stroke=0)

    def track(text, font, size, x, y, sp, color, right=False, center=False):
        c.setFillColor(color); c.setFont(font, size)
        total = sum(_sw(ch, font, size) + sp for ch in text) - (sp if text else 0)
        xx = (x - total) if right else ((x - total / 2.0) if center else x)
        for ch in text:
            c.drawString(xx, y, ch); xx += _sw(ch, font, size) + sp

    def seal_teal(cx, cy, r, name, branch):
        c.setStrokeColor(TEAL); c.setLineWidth(1.6); c.circle(cx, cy, r, stroke=1, fill=0)
        c.setLineWidth(0.7); c.circle(cx, cy, r - 5, stroke=1, fill=0)
        c.setStrokeColor(GOLD); c.setLineWidth(0.6); c.setDash(1, 2)
        c.circle(cx, cy, r - 9, stroke=1, fill=0); c.setDash()
        initials = ''.join(w[0] for w in (name or 'S').split()[:2]).upper() or 'S'
        c.setFillColor(TEAL); c.setFont('Times-Bold', max(9, int(r * 0.5)))
        c.drawCentredString(cx, cy - r * 0.18, initials)

        def arc(text, radius, start_deg, end_deg, size):
            text = (text or '').upper()
            if not text:
                return
            n = len(text); span = end_deg - start_deg
            c.setFont('Helvetica-Bold', size); c.setFillColor(TEAL)
            for i, ch in enumerate(text):
                a = start_deg + span * (i + 0.5) / n
                rad = math.radians(a)
                x = cx + radius * math.cos(rad); y = cy + radius * math.sin(rad)
                c.saveState(); c.translate(x, y); c.rotate(a - 90)
                c.drawCentredString(0, 0, ch); c.restoreState()

        fs = max(4.4, r * 0.135)
        arc((name or '')[:24], r - 2.6, 158, 22, fs)                 # top arc (upright)
        arc(branch or 'MAIN CAMPUS', r - 2.6, 292, 248, fs)          # bottom arc (upright)

    # ---- 1 · masthead ------------------------------------------------------
    logo = ctx['school'].get('logo_path') if show.get('school_logo') else None
    top = H - 42
    lw = lh = 0
    if logo:
        lw, lh = 66, 74
        try:
            c.drawImage(logo, FM, top - lh, lw, lh, preserveAspectRatio=True, anchor='nw', mask='auto')
        except Exception:
            lw = lh = 0
    name_x = FM + (lw + 16 if lw else 0)
    ny = top - 20
    if show.get('school_name') and ctx['school'].get('name'):
        for ln in _wrap(c, ctx['school']['name'].upper(), 'Times-Bold', 19, 250)[:2]:
            c.setFillColor(NAVY); c.setFont('Times-Bold', 19); c.drawString(name_x, ny, ln); ny -= 21
    if show.get('branch'):
        track((ctx.get('branch') or 'Main Campus').upper(), 'Helvetica', 8, name_x, ny - 1, 1.2, GRAY); ny -= 12
    elif show.get('school_motto') and ctx['school'].get('motto'):
        c.setFillColor(GRAY); c.setFont('Helvetica-Oblique', 8.5); c.drawString(name_x, ny - 1, ctx['school']['motto'])
    # right — WASSCE / year
    track('WASSCE', 'Helvetica-Bold', 14, R, top - 14, 1.5, NAVY, right=True)
    if show.get('exam_year'):
        c.setFillColor(NAVY); c.setFont('Times-Bold', 34); c.drawRightString(R, top - 50, str(ctx['exam']['year']))
    # fine gold connector between the branding and the examination identity
    cyc = top - 20
    gx1 = R - _sw('WASSCE', 'Helvetica-Bold', 14) - 5 * 1.5 - 14
    gx0 = name_x + 250
    if gx0 < gx1 - 20:
        c.setStrokeColor(GOLD); c.setLineWidth(1.2); c.line(gx0, cyc, gx1, cyc)
        c.setFillColor(GOLD)
        c.rect(gx0 - 4, cyc - 2, 4, 4, fill=1, stroke=0); c.rect(gx1, cyc - 2, 4, 4, fill=1, stroke=0)

    # ---- 2 · vertical WASSCE marker ---------------------------------------
    #  One continuous rule, broken only where the rotated label sits; the two
    #  segment ends adjacent to the label are picked out in antique gold. The
    #  rule runs close to the results column, not out in the far margin.
    mk_x = 68; mk_top = H - 152; mk_bot = 232
    mid = (mk_top + mk_bot) / 2.0
    half = (sum(_sw(ch, 'Helvetica-Bold', 8.5) + 3 for ch in 'WASSCE') - 3) / 2.0
    gap_t = mid + half + 6; gap_b = mid - half - 6
    c.setStrokeColor(GOLD); c.setLineWidth(1.3)
    c.line(mk_x, gap_t, mk_x, gap_t + 15); c.line(mk_x, gap_b, mk_x, gap_b - 15)
    c.setStrokeColor(NAVY); c.setLineWidth(1.0)
    c.line(mk_x, gap_t + 15, mk_x, mk_top); c.line(mk_x, gap_b - 15, mk_x, mk_bot)
    c.saveState(); c.translate(mk_x, mid); c.rotate(90)
    track('WASSCE', 'Helvetica-Bold', 8.5, 0, -3, 3, NAVY, center=True)
    c.restoreState()

    LM = 92
    # ---- 3 · examination label --------------------------------------------
    if show.get('exam_name'):
        track('WEST AFRICAN SENIOR SCHOOL', 'Helvetica-Bold', 9.5, LM, H - 150, 1.4, GRAY)
        track('CERTIFICATE EXAMINATION', 'Helvetica-Bold', 9.5, LM, H - 163, 1.4, GRAY)
        seg = ['WASSCE'] + ([str(ctx['exam']['year'])] if show.get('exam_year') else [])
        c.setFillColor(CHAR); c.setFont('Helvetica-Bold', 11); c.drawString(LM, H - 182, '  ·  '.join(seg))

    # ---- 4 · portrait ------------------------------------------------------
    photo_on = bool(show.get('student_photo') and ctx['student'].get('photo_path'))
    pw, ph = 100, 126; px = R - pw; py = H - 158 - ph
    if photo_on:
        c.setFillColor(colors.white); c.rect(px - 5, py - 5, pw + 10, ph + 10, fill=1, stroke=0)
        c.setStrokeColor(HAIR); c.setLineWidth(1.0); c.rect(px - 5, py - 5, pw + 10, ph + 10, stroke=1, fill=0)
        try:
            c.drawImage(ctx['student']['photo_path'], px, py, pw, ph, preserveAspectRatio=True, anchor='c', mask='auto')
        except Exception:
            c.setFillColor(colors.HexColor('#dfe3e8')); c.rect(px, py, pw, ph, fill=1, stroke=0)

    # ---- 5 · student identity ---------------------------------------------
    name_w = (px - 18 - LM) if photo_on else (R - LM)
    sy = H - 226
    if show.get('student_name'):
        nm = ctx['student']['name'].upper()
        nfs = 27
        while nfs > 19 and _sw(nm, 'Times-Bold', nfs) > name_w:
            nfs -= 1
        for ln in _wrap(c, nm, 'Times-Bold', nfs, name_w)[:2]:
            c.setFillColor(CHAR); c.setFont('Times-Bold', nfs); c.drawString(LM, sy, ln); sy -= nfs + 2
    meta = []
    if show.get('candidate_no') and ctx['student'].get('candidate_no'):
        meta.append((cfg.get('candidate_label') or 'CANDIDATE NO.') + ' ' + str(ctx['student']['candidate_no']))
    if show.get('admission_no') and ctx['student'].get('admission_no'):
        meta.append('ADMISSION NO. ' + str(ctx['student']['admission_no']))
    if show.get('exam_number') and ctx['student'].get('exam_number'):
        meta.append('EXAM NO. ' + str(ctx['student']['exam_number']))
    if show.get('student_class') and ctx['student'].get('klass'):
        meta.append('CLASS ' + str(ctx['student']['klass']))
    for m in meta:
        c.setFillColor(CHAR); c.setFont('Helvetica', 10.5); c.drawString(LM, sy, m); sy -= 14

    # ---- 6 · academic results ---------------------------------------------
    head_y = H - 322
    track('ACADEMIC RESULTS', 'Helvetica-Bold', 12.5, LM, head_y, 2.0, CHAR)
    c.setStrokeColor(NAVY); c.setLineWidth(1.2); c.line(LM, head_y - 11, R, head_y - 11)
    ch_y = head_y - 30
    track('NUMBER', 'Helvetica-Bold', 8.5, LM, ch_y, 1.2, GRAY)
    track('SUBJECT', 'Helvetica-Bold', 8.5, LM + 56, ch_y, 1.2, GRAY)
    track('GRADE', 'Helvetica-Bold', 8.5, R, ch_y, 1.2, GRAY, right=True)
    c.setStrokeColor(NAVY); c.setLineWidth(1.0); c.line(LM, ch_y - 8, R, ch_y - 8)

    results = ctx['results']; n = len(results)
    rows_top = ch_y - 8; table_bottom = 226
    rh = min(34, max(19, (rows_top - table_bottom) / max(n, 1)))
    subj_fs = 11 if rh >= 24 else 10
    if show.get('subjects') and n:
        for i, r in enumerate(results):
            ytop = rows_top - i * rh; ybot = ytop - rh
            if i % 2 == 1:
                c.setFillColor(BAND); c.rect(LM, ybot, R - LM, rh, fill=1, stroke=0)
            base = ybot + rh * 0.34
            c.setFillColor(GRAY); c.setFont('Helvetica', 8.5); c.drawString(LM, base + 1, f'{i + 1:02d}')
            subj = r['subject']
            if show.get('grade_desc') and r.get('desc'):
                subj = f"{subj}  ·  {r['desc']}"
            c.setFillColor(CHAR); c.setFont('Helvetica', subj_fs); c.drawString(LM + 56, base, subj + '  —')
            if show.get('grades'):
                c.setFillColor(NAVY); c.setFont('Helvetica-Bold', subj_fs + 4); c.drawRightString(R, base, r['grade'])
            c.setStrokeColor(HAIR); c.setLineWidth(0.6); c.line(LM, ybot, R, ybot)

    # ---- 7 · editorial stat line ------------------------------------------
    st = ctx['stats']; stats = []
    if show.get('total_subjects'): stats.append((f"{st['total']:02d}", 'SUBJECTS'))
    if show.get('a1_count'):       stats.append((f"{st['a1']:02d}", 'A1 GRADES'))
    if show.get('credits'):        stats.append((f"{st['credits']:02d}", 'CREDITS'))
    if show.get('average'):        stats.append((str(st['average']), 'AVERAGE'))
    if show.get('classification'): stats.append((st['classification'].upper(), 'CLASS'))
    if stats:
        sum_top, sum_y, sum_bot = 214, 190, 166
        c.setStrokeColor(HAIR); c.setLineWidth(0.8)
        c.line(LM, sum_top, R, sum_top); c.line(LM, sum_bot, R, sum_bot)
        colw = (R - LM) / len(stats)
        for i, (v, l) in enumerate(stats):
            cx = LM + colw * i + 20
            c.setFillColor(NAVY); c.setFont('Times-Bold', 21); c.drawString(cx, sum_y, v)
            track(l, 'Helvetica-Bold', 7.5, cx + _sw(v, 'Times-Bold', 21) + 8, sum_y + 5, 0.8, GRAY)
            if i:
                sepx = LM + colw * i
                c.setStrokeColor(HAIR); c.setLineWidth(0.8); c.line(sepx, sum_bot + 6, sepx, sum_top - 6)

    # ---- 8 · authentication row -------------------------------------------
    sig_line_y = 118
    if show.get('principal_signature') or show.get('principal_name'):
        sig = ctx['official'].get('signature_path') if show.get('principal_signature') else None
        if sig:
            try:
                c.drawImage(sig, LM, sig_line_y + 2, 120, 30, preserveAspectRatio=True, anchor='sw', mask='auto')
            except Exception:
                sig = None
        if not sig:
            c.setFillColor(CHAR); c.setFont('Times-Italic', 17); c.drawString(LM, sig_line_y + 6, 'Principal Signature')
        c.setStrokeColor(HAIR); c.setLineWidth(0.8); c.line(LM, sig_line_y, LM + 168, sig_line_y)
        pn = ctx['official'].get('principal_name') if show.get('principal_name') else None
        c.setFillColor(CHAR); c.setFont('Helvetica-Bold', 9.5); c.drawString(LM, sig_line_y - 14, pn or 'Principal Signature')
        c.setFillColor(GRAY); c.setFont('Helvetica', 8); c.drawString(LM, sig_line_y - 25, 'Principal')
    if show.get('school_stamp'):
        seal_teal(300, 106, 33, ctx['school'].get('name'), ctx.get('branch'))
    vx = 352; vy = 130
    if show.get('verification_code') or show.get('date_issued') or (show.get('qr_code') and verify_url):
        c.setFillColor(NAVY); c.setFont('Helvetica-Bold', 10.5); c.drawString(vx, vy, 'Verification')
        row = vy - 15
        if show.get('verification_code') and ctx.get('verify_code'):
            c.setFillColor(GRAY); c.setFont('Helvetica', 7.5); c.drawString(vx, row, 'Verification No.')
            c.setFillColor(CHAR); c.setFont('Helvetica-Bold', 8.5); c.drawString(vx, row - 11, str(ctx['verify_code'])); row -= 26
        if show.get('date_issued'):
            c.setFillColor(CHAR); c.setFont('Helvetica', 8)
            c.drawString(vx, row, 'Date Issued: ' + _issue_date().strftime('%d %B %Y'))
        if show.get('qr_code') and verify_url:
            try:
                import qrcode
                qb = io.BytesIO(); qrcode.make(verify_url).save(qb, format='PNG'); qb.seek(0)
                c.drawImage(ImageReader(qb), R - 56, 82, 56, 56, mask='auto')
            except Exception:
                pass

    # ---- 9 · footer -------------------------------------------------------
    fparts = []
    seg1 = ctx['school'].get('name', '') or ''
    if show.get('school_address') and ctx['school'].get('address'):
        seg1 = (seg1 + ' · ' + ctx['school']['address']).strip(' ·')
    if seg1:
        fparts.append(seg1)
    if show.get('footer_contact') and ctx['school'].get('phone'):
        fparts.append(ctx['school']['phone'])
    if show.get('footer_contact') and ctx['school'].get('email'):
        fparts.append(ctx['school']['email'])
    if show.get('footer_website') and ctx['school'].get('website'):
        fparts.append(ctx['school']['website'])
    if show.get('footer_custom') and cfg.get('footer_text'):
        fparts = [cfg['footer_text']]
    if fparts:
        c.setStrokeColor(HAIR); c.setLineWidth(0.8); c.line(FM, 52, R, 52)
        c.setFillColor(GRAY); c.setFont('Helvetica', 7.5); c.drawCentredString(W / 2, 36, '   ·   '.join(fparts))


# ===========================================================================
#  Design 12 — TERRAIN 2026 (contemporary architectural, African modernism)
#  A split masthead (school identity left, a plum architectural block with a
#  large serif year right), a warm-sand field, an oversized deep-plum student
#  name over a faint cropped "26" motif beside an offset-framed portrait, an
#  editorial NUMBER · SUBJECT · GRADE record over hairline rules, a plum/
#  terracotta achievement band, and a restrained signature / seal / QR row.
#  Terracotta + plum + sage on sand — deliberately unlike the other designs.
# ===========================================================================
def _draw_terrain(c, ctx, show, cfg, verify_url):
    from reportlab.lib.utils import ImageReader
    W, H = A4
    TERRA = colors.HexColor('#B94E3D'); PLUM = colors.HexColor('#432A3A')
    SAGE = colors.HexColor('#82917A'); SAND = colors.HexColor('#EFE5D2')
    CREAM = colors.HexColor('#FAF7F0'); ESP = colors.HexColor('#292321')
    MUTE = colors.HexColor('#776D68'); LINE = colors.HexColor('#d5c9b1')
    GHOST = colors.HexColor('#d8c3a0')
    FM = 40; R = W - FM
    c.setFillColor(CREAM); c.rect(0, 0, W, H, fill=1, stroke=0)

    def track(text, font, size, x, y, sp, color, right=False, center=False):
        c.setFillColor(color); c.setFont(font, size)
        total = sum(_sw(ch, font, size) + sp for ch in text) - (sp if text else 0)
        xx = (x - total) if right else ((x - total / 2.0) if center else x)
        for ch in text:
            c.drawString(xx, y, ch); xx += _sw(ch, font, size) + sp

    def seal_ring(cx, cy, r, name, branch):
        c.setStrokeColor(ESP); c.setLineWidth(1.3); c.circle(cx, cy, r, stroke=1, fill=0)
        c.setStrokeColor(SAGE); c.setLineWidth(0.7); c.circle(cx, cy, r - 4.5, stroke=1, fill=0)
        initials = ''.join(w[0] for w in (name or 'S').split()[:2]).upper() or 'S'
        c.setFillColor(PLUM); c.setFont('Times-Bold', max(9, int(r * 0.5)))
        c.drawCentredString(cx, cy - r * 0.18, initials)
        import math

        def arc(text, radius, start_deg, end_deg, size, color):
            text = (text or '').upper()
            if not text:
                return
            nn = len(text); span = end_deg - start_deg
            c.setFont('Helvetica-Bold', size); c.setFillColor(color)
            for i, ch in enumerate(text):
                a = start_deg + span * (i + 0.5) / nn
                rad = math.radians(a)
                x = cx + radius * math.cos(rad); y = cy + radius * math.sin(rad)
                c.saveState(); c.translate(x, y); c.rotate(a - 90)
                c.drawCentredString(0, 0, ch); c.restoreState()
        fs = max(4.2, r * 0.13)
        arc((name or '')[:24], r - 2.4, 158, 22, fs, ESP)
        arc(branch or 'MAIN CAMPUS', r - 2.4, 292, 248, fs, ESP)

    # ---- 1 · split masthead -----------------------------------------------
    # right architectural block (plum) with terracotta accents
    bx = 356
    c.setFillColor(PLUM); c.rect(bx, H - 160, W - bx, 160 + 3, fill=1, stroke=0)   # +3 bleed to top
    c.setFillColor(TERRA); c.rect(470, H - 42, W - 470 + 3, 42 + 3, fill=1, stroke=0)   # top-right accent
    c.setFillColor(TERRA); c.rect(W - 7, H - 152, 7 + 3, 34, fill=1, stroke=0)          # right-edge tab
    yr = str(ctx['exam'].get('year', ''))
    track('WASSCE', 'Helvetica-Bold', 21, bx + 22, H - 60, 1.0, CREAM)
    if show.get('exam_year'):
        c.setFillColor(CREAM); c.setFont('Times-Bold', 44); c.drawString(bx + 20, H - 112, yr)
    # left identity
    logo = ctx['school'].get('logo_path') if show.get('school_logo') else None
    lw = lh = 0
    if logo:
        lw, lh = 52, 60
        try:
            c.drawImage(logo, FM, H - 42 - lh, lw, lh, preserveAspectRatio=True, anchor='nw', mask='auto')
        except Exception:
            lw = lh = 0
    nx = FM + (lw + 14 if lw else 0); ny = H - 58
    if show.get('school_name') and ctx['school'].get('name'):
        for ln in _wrap(c, ctx['school']['name'].upper(), 'Helvetica-Bold', 20, 236)[:2]:
            c.setFillColor(PLUM); c.setFont('Helvetica-Bold', 20); c.drawString(nx, ny, ln); ny -= 21
    # campus line: the student's branch when the school has branches, otherwise
    # the default "MAIN CAMPUS" label
    campus = (ctx.get('branch') if (show.get('branch') and ctx.get('branch')) else None) or 'MAIN CAMPUS'
    track(campus.upper(), 'Helvetica', 10, nx, ny - 1, 1.0, MUTE)

    # sand identity field — the name/photo/motif zone sits on the warmer sand
    # tone while the rest of the page is the lighter cream. Its top edge meets
    # the header (plum block bottom) and it stops short of the right edge (a
    # cream margin remains), exactly as the reference.
    id_top, id_bot = H - 160, H - 396
    band_right = W - 49
    c.setFillColor(SAND); c.rect(0, id_bot, band_right, id_top - id_bot, fill=1, stroke=0)

    # ---- 2 · examination label --------------------------------------------
    c.setStrokeColor(SAGE); c.setLineWidth(0.8); c.line(FM, id_top, 340, id_top)
    if show.get('exam_name'):
        track('WEST AFRICAN SENIOR SCHOOL', 'Helvetica-Bold', 9, FM, H - 188, 1.2, ESP)
        track('CERTIFICATE EXAMINATION', 'Helvetica-Bold', 9, FM, H - 200, 1.2, ESP)
        c.setFillColor(ESP); c.setFont('Helvetica-Bold', 15); c.drawString(FM, H - 222, 'WASSCE')

    # ---- 3 · student identity + cropped portrait --------------------------
    photo_on = bool(show.get('student_photo') and ctx['student'].get('photo_path'))
    pw, ph = 100, 126; px = band_right - pw - 22; py = H - 238 - ph   # inside the sand band
    # faint architectural year motif behind the name
    if show.get('exam_year') and len(yr) >= 2:
        c.setFillColor(GHOST); c.setFont('Times-Bold', 205); c.drawString(212, H - 364, yr[-2:])
    name_w = (px - 26 - FM) if photo_on else (R - FM)
    sy = H - 264
    if show.get('student_name'):
        words = ctx['student']['name'].upper().split() or ['']
        if len(words) > 4:                       # fold overflow words into the last line
            words = words[:3] + [' '.join(words[3:])]
        nfs = 44
        while nfs > 24 and max(_sw(w, 'Times-Bold', nfs) for w in words) > name_w:
            nfs -= 1
        for ln in words:                         # one name part per line (architectural)
            c.setFillColor(PLUM); c.setFont('Times-Bold', nfs); c.drawString(FM, sy, ln); sy -= nfs + 4
        sy += (nfs - 8)                           # pull metadata up close under the last line
    meta = []
    if show.get('candidate_no') and ctx['student'].get('candidate_no'):
        meta.append((cfg.get('candidate_label') or 'CANDIDATE NO.') + ' ' + str(ctx['student']['candidate_no']))
    if show.get('admission_no') and ctx['student'].get('admission_no'):
        meta.append('ADMISSION NO. ' + str(ctx['student']['admission_no']))
    if show.get('exam_number') and ctx['student'].get('exam_number'):
        meta.append('EXAM NO. ' + str(ctx['student']['exam_number']))
    if show.get('student_class') and ctx['student'].get('klass'):
        meta.append('CLASS ' + str(ctx['student']['klass']))
    for m in meta:
        c.setFillColor(MUTE); c.setFont('Helvetica', 9, ); c.drawString(FM, sy, m); sy -= 13
    if photo_on:
        c.setFillColor(CREAM); c.rect(px - 6, py - 6, pw + 12, ph + 12, fill=1, stroke=0)
        try:
            c.drawImage(ctx['student']['photo_path'], px, py, pw, ph, preserveAspectRatio=True, anchor='c', mask='auto')
        except Exception:
            c.setFillColor(colors.HexColor('#cbb9a6')); c.rect(px, py, pw, ph, fill=1, stroke=0)
        c.setStrokeColor(TERRA); c.setLineWidth(3); c.rect(px - 6, py - 6, pw + 12, ph + 12, stroke=1, fill=0)
        c.setFillColor(SAGE)                                   # sage alignment tabs
        cxp = px + pw / 2.0; cyp = py + ph / 2.0
        c.rect(cxp - 4, py + ph - 3, 8, 18, fill=1, stroke=0)         # top edge — vertical, centred
        c.rect(cxp - 4, py - 15, 8, 18, fill=1, stroke=0)            # bottom edge — vertical, centred
        c.rect(px + pw - 3, cyp - 4, 18, 8, fill=1, stroke=0)         # right edge — horizontal, centred

    # ---- 4 · academic results ---------------------------------------------
    head_y = H - 424
    c.setFillColor(TERRA); c.rect(28, head_y - 3, 22, 15, fill=1, stroke=0)
    track('ACADEMIC RESULTS', 'Helvetica-Bold', 14, 62, head_y, 1.5, ESP)

    results = ctx['results']; n = len(results)
    rows_top = head_y - 18; table_bottom = 236
    rh = min(30, (rows_top - table_bottom) / max(n, 1))     # shrink to fit, never overflow
    subj_fs = 11 if rh >= 22 else (10 if rh >= 16.5 else 9)
    grade_fs = subj_fs + (6 if rh >= 22 else (4 if rh >= 16.5 else 3))
    num_x, subj_x = 62, 100
    if show.get('subjects') and n:
        c.setStrokeColor(LINE); c.setLineWidth(0.7); c.line(FM, rows_top, R, rows_top)
        for i, r in enumerate(results):
            ytop = rows_top - i * rh; ybot = ytop - rh
            base = ybot + rh * 0.30
            c.setFillColor(ESP); c.setFont('Helvetica', min(10, subj_fs)); c.drawString(num_x, base, f'{i + 1:02d}')
            subj = r['subject'].upper()
            if show.get('grade_desc') and r.get('desc'):
                subj = f"{subj}  ·  {r['desc'].upper()}"
            c.setFillColor(ESP); c.setFont('Helvetica', subj_fs); c.drawString(subj_x, base, subj)
            if show.get('grades'):
                gc = TERRA if i % 2 else PLUM
                c.setFillColor(gc); c.setFont('Helvetica-Bold', grade_fs); c.drawRightString(R, base, r['grade'])
            c.setStrokeColor(LINE); c.setLineWidth(0.7); c.line(FM, ybot, R, ybot)

    # ---- 5 · achievement band ---------------------------------------------
    st = ctx['stats']; stats = []
    if show.get('total_subjects'): stats.append((f"{st['total']:02d}", 'SUBJECTS'))
    if show.get('a1_count'):       stats.append((f"{st['a1']:02d}", 'A1'))
    if show.get('credits'):        stats.append((f"{st['credits']:02d}", 'CREDITS'))
    if show.get('average'):        stats.append((str(st['average']), 'AVERAGE'))
    if show.get('classification'): stats.append((st['classification'].upper(), 'CLASS'))
    if stats:
        by0, bh = 182, 42; by1 = by0 + bh; nseg = len(stats); segw = (R - FM) / nseg
        c.saveState()
        p = c.beginPath(); p.roundRect(FM, by0, R - FM, bh, 7); c.clipPath(p, stroke=0, fill=0)
        c.setFillColor(PLUM); c.rect(FM, by0, R - FM, bh, fill=1, stroke=0)
        c.setFillColor(TERRA); c.rect(FM + segw * (nseg - 1), by0, segw, bh, fill=1, stroke=0)
        c.restoreState()
        for i, (v, l) in enumerate(stats):
            cx0 = FM + segw * i
            if i:
                c.setStrokeColor(SAGE); c.setLineWidth(0.9); c.line(cx0, by0 + 9, cx0, by1 - 9)
            vw = _sw(v, 'Times-Bold', 21); lw2 = _sw(l, 'Helvetica-Bold', 8)
            gx = cx0 + (segw - (vw + 7 + lw2)) / 2.0
            c.setFillColor(CREAM); c.setFont('Times-Bold', 21); c.drawString(gx, by0 + 14, v)
            track(l, 'Helvetica-Bold', 8, gx + vw + 7, by0 + 18, 0.8, CREAM)

    # ---- 6 · verification -------------------------------------------------
    sig_y = 126
    if show.get('principal_signature') or show.get('principal_name'):
        sig = ctx['official'].get('signature_path') if show.get('principal_signature') else None
        if sig:
            try:
                c.drawImage(sig, FM, sig_y + 2, 120, 30, preserveAspectRatio=True, anchor='sw', mask='auto')
            except Exception:
                sig = None
        if not sig:
            c.setFillColor(ESP); c.setFont('Times-Italic', 15); c.drawString(FM, sig_y + 6, 'Principal signature')
        c.setStrokeColor(SAGE); c.setLineWidth(0.8); c.line(FM, sig_y, FM + 168, sig_y)
        pn = ctx['official'].get('principal_name') if show.get('principal_name') else None
        c.setFillColor(ESP); c.setFont('Helvetica-Bold', 9); c.drawString(FM, sig_y - 13, pn or 'Principal name')
    if show.get('school_stamp'):
        seal_ring(285, 106, 30, ctx['school'].get('name'), ctx.get('branch'))
    if show.get('verification_code') and ctx.get('verify_code'):
        c.setFillColor(ESP); c.setFont('Helvetica-Bold', 9.5); c.drawString(352, 116, str(ctx['verify_code']))
        c.setFillColor(MUTE); c.setFont('Helvetica', 7.5); c.drawString(352, 103, 'Verification')
    if show.get('qr_code') and verify_url:
        try:
            import qrcode
            qb = io.BytesIO(); qrcode.make(verify_url).save(qb, format='PNG'); qb.seek(0)
            c.setFillColor(CREAM); c.rect(R - 56, 92, 56, 56, fill=1, stroke=0)
            c.drawImage(ImageReader(qb), R - 54, 94, 52, 52, mask='auto')
        except Exception:
            pass
    if show.get('date_issued'):
        c.setFillColor(MUTE); c.setFont('Helvetica', 7.5)
        c.drawRightString(R, 80, 'Date issued · ' + _issue_date().strftime('%d %b %Y'))

    # ---- 7 · footer -------------------------------------------------------
    fp = []
    seg1 = ctx['school'].get('name', '') or ''
    if show.get('school_address') and ctx['school'].get('address'):
        seg1 = (seg1 + ' · ' + ctx['school']['address']).strip(' ·')
    if seg1:
        fp.append(seg1)
    line2 = []
    if show.get('footer_contact') and ctx['school'].get('phone'):
        line2.append(ctx['school']['phone'])
    if show.get('footer_contact') and ctx['school'].get('email'):
        line2.append(ctx['school']['email'])
    if show.get('footer_website') and ctx['school'].get('website'):
        line2.append(ctx['school']['website'])
    if show.get('footer_custom') and cfg.get('footer_text'):
        fp = [cfg['footer_text']]; line2 = []
    if fp or line2:
        c.setStrokeColor(LINE); c.setLineWidth(0.8); c.line(FM, 52, R, 52)
        c.setFillColor(SAGE); c.rect(W / 2 - 4, 48, 8, 8, fill=1, stroke=0)
        c.setFillColor(MUTE); c.setFont('Helvetica', 7.5)
        if fp:
            c.drawCentredString(W / 2, 34, '   ·   '.join(fp))
        if line2:
            c.drawCentredString(W / 2, 23, '   ·   '.join(line2))


def _sw(text, font, size):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    return stringWidth(text, font, size)


_CANVAS_DRAW = {
    'prestige': _draw_prestige, 'classic': _draw_classic, 'editorial': _draw_editorial,
    'premium': _draw_premium, 'contemporary': _draw_contemporary, 'creative': _draw_creative,
    'executive': _draw_executive, 'profile': _draw_profile, 'meridian': _draw_meridian,
    'aurelis': _draw_aurelis, 'monument': _draw_monument, 'terrain': _draw_terrain,
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
