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
    'classic':      {'name': 'Classic Academic',
                     'desc': 'Formal, centred certificate-style composition with a double rule border.',
                     'landscape': False},
    'editorial':    {'name': 'Modern Editorial',
                     'desc': 'Asymmetric layout with a bold typographic masthead and a side rail.',
                     'landscape': False},
    'premium':      {'name': 'Premium Certificate',
                     'desc': 'Elegant certificate with an ornate gold-toned frame and seal area.',
                     'landscape': True},
    'contemporary': {'name': 'Contemporary Report',
                     'desc': 'Structured card grid — student panel beside a clean results table.',
                     'landscape': False},
    'creative':     {'name': 'Creative Academic',
                     'desc': 'Expressive geometric header band with a two-tone accent block.',
                     'landscape': False},
}
DEFAULT_TEMPLATE = 'classic'


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
         'avail': lambda c: _has(c, 'official', 'stamp_path')},
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


def render_pdf(ctx, template_key, show, cfg=None, verify_url=None):
    """Deterministically render the result to a PDF (BytesIO)."""
    cfg = cfg or {}
    key = template_key if template_key in _LAYOUTS else DEFAULT_TEMPLATE
    primary = ctx['brand']['primary']
    accent = ctx['brand']['accent']
    S = _styles(primary, accent)
    land = is_landscape(key)
    pagesize = landscape(A4) if land else A4
    margins = (18, 18, 16, 16) if land else (16, 18, 16, 16)
    mt, mb, ml, mr = margins
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=pagesize, leftMargin=ml * mm, rightMargin=mr * mm,
                            topMargin=mt * mm, bottomMargin=mb * mm,
                            title=f"WAEC {ctx['exam']['year']} — {ctx['student']['name']}")
    body = _LAYOUTS[key](ctx, show, cfg, S, verify_url)
    frame_w = pagesize[0] - (ml + mr) * mm
    frame_h = pagesize[1] - (mt + mb) * mm
    story = [KeepInFrame(frame_w, frame_h, body, mode='shrink', hAlign='CENTER', vAlign='TOP')]
    dec = _border_for(key, primary, accent)
    pdf.build(story, onFirstPage=dec, onLaterPages=dec)
    buf.seek(0)
    return buf


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
