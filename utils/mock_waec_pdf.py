"""Server-side PDFs for Mock WAEC — broadsheet, blank recording sheet and result
slips. Rendered with reportlab (no headless browser) so they preview/print the
same everywhere. School identity comes from SchoolSettings; an ``opts`` dict
controls which optional blocks (COMPETENCE banner, address, contact, motto,
summary, signatures) are included.
"""
import io

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                Spacer, PageBreak, Flowable)
from reportlab.pdfbase.pdfmetrics import stringWidth
from utils.web_exports import pdf_escape

_BLACK = colors.black
_HEAD = colors.HexColor('#d9d9d9')
_FOOT = colors.HexColor('#eeeeee')
_SHADE = colors.HexColor('#cfcfcf')

# WASSCE grade bands (mirror models.mock_waec.waec_grade_from_score). Credit = C6+.
_GRADE_KEY = [('A1', '75–100'), ('B2', '70–74'), ('B3', '65–69'), ('C4', '60–64'),
              ('C5', '55–59'), ('C6', '50–54'), ('D7', '45–49'), ('E8', '40–44'),
              ('F9', '0–39')]
_BLANK_SUMMARY = ['No. offered', 'No. passed (C6+)', 'No. failed',
                  'Average score %', 'Average grade']
_EXTRA_ROWS = 3        # blank rows before the summary, for hand-written additions


class _VHead(Flowable):
    """A column header drawn vertically (bottom-to-top), like the on-screen
    broadsheet — lets subject columns stay narrow while showing full names."""
    def __init__(self, text, size=8, pad=6):
        Flowable.__init__(self)
        self.text = text or ''
        self.size = size
        self.pad = pad

    def wrap(self, aw, ah):
        self.width = self.size + 2
        self.height = stringWidth(self.text, 'Helvetica-Bold', self.size) + self.pad
        return (self.width, self.height)

    def draw(self):
        c = self.canv
        c.saveState()
        c.translate(self.size, self.pad / 2.0)
        c.rotate(90)
        c.setFont('Helvetica-Bold', self.size)
        c.drawString(0, -self.size * 0.28, self.text)
        c.restoreState()

_S = {}


def _styles():
    if _S:
        return _S
    base = getSampleStyleSheet()
    _S['school'] = ParagraphStyle('sch', parent=base['Title'], fontSize=18, leading=20,
                                  alignment=TA_CENTER, spaceAfter=0, textColor=_BLACK)
    _S['addr'] = ParagraphStyle('addr', parent=base['Normal'], fontSize=9,
                                alignment=TA_CENTER, spaceAfter=0)
    _S['comp'] = ParagraphStyle('comp', parent=base['Normal'], fontSize=14,
                                alignment=TA_CENTER, spaceBefore=4, spaceAfter=2,
                                fontName='Helvetica-Bold')
    _S['exam'] = ParagraphStyle('exam', parent=base['Normal'], fontSize=11,
                                alignment=TA_CENTER, spaceAfter=6, fontName='Helvetica-Bold')
    _S['colhead'] = ParagraphStyle('ch', parent=base['Normal'], fontSize=7.5, leading=8.5,
                                   alignment=TA_CENTER, fontName='Helvetica-Bold')
    _S['name'] = ParagraphStyle('nm', parent=base['Normal'], fontSize=8.5, leading=9.5,
                                fontName='Helvetica-Bold')
    _S['cell'] = ParagraphStyle('c', parent=base['Normal'], fontSize=10)
    return _S


def _opt(opts, key, default=True):
    return default if opts is None else opts.get(key, default)


def _short_name(st):
    """Surname + first name only for the broadsheet name column — the middle name
    is dropped so the column can stay narrow and leave more room for the score /
    grade boxes."""
    parts = [st.surname or '', st.first_name or '']
    return ' '.join(p for p in parts if p).strip() or st.full_name


def _school_header(e, school, opts, subtitle):
    """School identity block + optional COMPETENCE RESULT banner + a subtitle.

    When a logo is uploaded it sits to the left of the centred name/address block
    (letterhead style); otherwise the text block is centred on its own."""
    _styles()
    # (paragraph, plain text, font, size) — text+font size the column so the logo
    # hugs the name block rather than sitting at the far-left margin.
    items = []
    if school.get('name'):
        nm = (school['name'] or '').upper()
        items.append((Paragraph(pdf_escape(nm), _S['school']), nm, 'Helvetica-Bold', 18))
    if _opt(opts, 'address') and school.get('address'):
        items.append((Paragraph(pdf_escape(school['address']), _S['addr']), school['address'], 'Helvetica', 9))
    if _opt(opts, 'contact'):
        contact = ' · '.join(x for x in (school.get('phone'), school.get('email')) if x)
        if contact:
            items.append((Paragraph(pdf_escape(contact), _S['addr']), contact, 'Helvetica', 9))
    if _opt(opts, 'motto') and school.get('motto'):
        items.append((Paragraph('<i>%s</i>' % pdf_escape(school['motto']), _S['addr']), school['motto'], 'Helvetica-Oblique', 9))
    block = [it[0] for it in items]
    logo = None
    if school.get('logo_path'):
        from utils.school import logo_flowable
        logo = logo_flowable(max_h_mm=18, max_w_mm=30, path=school.get('logo_path'))
    if logo is not None and block:
        from utils.school import logo_header_flowable
        e.append(logo_header_flowable(logo, items))
    else:
        e.extend(block)
    if _opt(opts, 'title'):
        e.append(Paragraph('COMPETENCE RESULT', _S['comp']))
    if subtitle:
        e.append(Paragraph(pdf_escape(subtitle), _S['exam']))


def _groups(subjects, per):
    return ([subjects[i:i + per] for i in range(0, len(subjects), per)]
            if per and len(subjects) > per else [subjects])


def _pagesize(orient):
    """A4, landscape by default. ``orient='portrait'`` for tall paper."""
    return A4 if orient == 'portrait' else landscape(A4)


def _grade_key_table(usable):
    """Compact WASSCE grade-band reference strip."""
    _styles()
    head = [Paragraph('Grade', _S['colhead'])] + [Paragraph(g, _S['colhead']) for g, _ in _GRADE_KEY]
    rng = [Paragraph('Score', _S['colhead'])] + [Paragraph(r, _S['colhead']) for _, r in _GRADE_KEY]
    label_w = 16 * mm
    cell_w = min(18 * mm, (usable - label_w) / len(_GRADE_KEY))
    t = Table([head, rng], colWidths=[label_w] + [cell_w] * len(_GRADE_KEY))
    t.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.7, _BLACK),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    return t


def _fit_per(usable, sn_w, name_w, reserve, min_w, per, n):
    """Largest subjects-per-sheet that keeps each subject column at least ``min_w``
    wide, so headers never collapse into an un-renderable sliver. A requested
    ``per`` (incl. 0 = "one wide page") is reduced to this when it wouldn't fit;
    the sheet then splits across pages instead of overflowing."""
    room = usable - sn_w - name_w - reserve
    fit = max(1, int(room / min_w)) if min_w > 0 else n
    if not per or per <= 0 or per > fit:
        return fit
    return per


def broadsheet_pdf(bs, exam, school, opts=None, per=8, orient='landscape'):
    """Full score+grade matrix. Wide subject sets split across pages (``per``
    columns each); no admission numbers. ``opts['summary']`` toggles the
    per-subject offered/passed/failed/average rows. ``orient`` is landscape or
    portrait A4, filling the page with an 8mm margin."""
    _styles()
    page = _pagesize(orient)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=page, topMargin=8 * mm,
                            bottomMargin=8 * mm, leftMargin=8 * mm, rightMargin=8 * mm,
                            title=f'Broadsheet — {exam.display_name}')
    usable = page[0] - 16 * mm
    sn_w, name_w = 9 * mm, 52 * mm
    # Vertical headers don't constrain width, so columns only need to fit a score.
    per = _fit_per(usable, sn_w, name_w, 24 * mm, 13 * mm, per, len(bs['subjects']))
    groups = _groups(bs['subjects'], per)
    ss = bs['subject_summary']
    nrows = len(bs['rows'])
    show_summary = _opt(opts, 'summary')
    e = []
    for gi, group in enumerate(groups):
        last = gi == len(groups) - 1
        sub = f'{exam.display_name} — Broadsheet'
        if len(groups) > 1:
            sub += f' (Sheet {gi + 1} of {len(groups)})'
        _school_header(e, school, opts, sub)

        tail = 2 if last else 0
        sub_w = (usable - sn_w - name_w) / (len(group) + tail)

        header = [Paragraph('S/N', _S['colhead']), Paragraph('Name of Student', _S['colhead'])]
        header += [_VHead(s) for s in group]                 # vertical subject names
        if last:
            header += [_VHead('Credits'), _VHead('Average %')]
        data = [header]
        for i, row in enumerate(bs['rows'], 1):
            line = [str(i), Paragraph(pdf_escape(_short_name(row['student'])), _S['name'])]
            for s in group:
                r = row['cells'].get(s)
                line.append(f'{r.score} {r.grade}' if (r and r.score is not None) else '')
            if last:
                line += [str(row['credits']),
                         (str(row['average_score']) if row['average_score'] is not None else '')]
            data.append(line)

        ncols = 2 + len(group) + tail
        for _ in range(_EXTRA_ROWS):                          # blank rows for additions
            data.append([''] * ncols)

        sum0 = nrows + 1 + _EXTRA_ROWS                        # first summary row index
        if show_summary:
            for label, fn in (('No. offered', lambda d: d['offered']),
                              ('No. passed (C6+)', lambda d: d['passed']),
                              ('No. failed', lambda d: d['failed']),
                              ('Average score %', lambda d: d['avg_score'] if d['avg_score'] is not None else '—'),
                              ('Average grade', lambda d: d['avg_grade'])):
                rr = ['', label] + [str(fn(ss[s])) for s in group]
                if last:
                    rr += ['', '']
                data.append(rr)

        widths = [sn_w, name_w] + [sub_w] * (len(group) + tail)
        heights = ([None] + [None] * nrows + [7.5 * mm] * _EXTRA_ROWS
                   + ([None] * len(_BLANK_SUMMARY) if show_summary else []))
        # repeatRows=0: the header (subject names, S/N, Name, Credits, Average)
        # appears on the first page only; an overflowing roster continues without
        # the header band repeating.
        t = Table(data, colWidths=widths, repeatRows=0, rowHeights=heights)
        style = [
            ('GRID', (0, 0), (-1, -1), 0.9, _BLACK),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, nrows), 9.5),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('VALIGN', (0, 0), (-1, 0), 'BOTTOM'),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ]
        if show_summary:
            style.append(('FONTSIZE', (0, sum0), (-1, -1), 8.5))
            style.append(('LINEABOVE', (0, sum0), (-1, sum0), 1.3, _BLACK))
        t.setStyle(TableStyle(style))
        e.append(t)
        if _opt(opts, 'grades'):
            e.append(Spacer(1, 6))
            e.append(_grade_key_table(usable))
        if not last:
            e.append(PageBreak())
    doc.build(e)
    buf.seek(0)
    return buf


def blank_broadsheet_pdf(students, offered, subjects, exam, school, opts=None,
                         per=0, orient='landscape'):
    """A blank recording sheet: student names down the side, every subject across
    the top with its own **Score** and **Grade** columns to write into. Landscape
    or portrait A4. (``offered`` is accepted for call compatibility but no longer
    used — cells are left plain rather than shading out non-offered subjects.)

    Columns are sized to fit the whole subject set on one sheet by default
    (``per=0``): with the full WAEC load (~16 subjects) all of them stay on one
    landscape page instead of spilling a few onto a second sheet. The score/grade
    columns are deliberately narrow (hand-writing a 2-digit score or a grade), so
    cell padding and the Score/Grade sub-labels are kept compact."""
    _styles()
    page = _pagesize(orient)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=page, topMargin=8 * mm,
                            bottomMargin=8 * mm, leftMargin=8 * mm, rightMargin=8 * mm,
                            title=f'Blank broadsheet — {exam.display_name}')
    usable = page[0] - 16 * mm
    # Surname + first name only, so the name column can be narrow and hand more
    # width to the Score/Grade boxes.
    sn_w, name_w = 8 * mm, 34 * mm
    # Two writable columns (Score + Grade) per subject. Reserve only ~13mm per
    # subject so the full WAEC set fits one landscape sheet; columns narrow before
    # the sheet splits.
    per = _fit_per(usable, sn_w, name_w, 0, 13 * mm, per, len(subjects))
    groups = _groups(subjects, per)
    nstud = len(students)
    e = []
    for gi, group in enumerate(groups):
        sub = f'{exam.display_name} — Recording Sheet'
        if len(groups) > 1:
            sub += f' (Sheet {gi + 1} of {len(groups)})'
        _school_header(e, school, opts, sub)

        pair_w = (usable - sn_w - name_w) / len(group)      # width per subject
        cell_w = pair_w / 2                                  # Score | Grade

        # Two-row header: the vertical subject name spanning its Score+Grade
        # columns, then the Score / Grade sub-labels (compact for narrow columns).
        h1 = [Paragraph('S/N', _S['colhead']), Paragraph('Name of Student', _S['colhead'])]
        h2 = ['', '']
        for s in group:
            h1 += [_VHead(s), '']
            h2 += [_VHead('Score', size=7), _VHead('Grade', size=7)]   # vertical sub-labels
        data = [h1, h2]
        for i, st in enumerate(students, 1):
            line = [str(i), Paragraph(pdf_escape(_short_name(st)), _S['name'])]
            line += ['', ''] * len(group)
            data.append(line)

        for _ in range(_EXTRA_ROWS):                        # blank rows for additions
            data.append(['', ''] + [''] * (2 * len(group)))

        # Blank summary rows for filling the per-subject tallies by hand.
        show_summary = _opt(opts, 'summary')
        sum0 = len(data)                        # table row of the first summary row
        if show_summary:
            for label in _BLANK_SUMMARY:
                data.append(['', Paragraph(pdf_escape(label), _S['name'])] + [''] * (2 * len(group)))

        widths = [sn_w, name_w] + [cell_w] * (2 * len(group))
        heights = ([None, None] + [8.5 * mm] * nstud + [8.5 * mm] * _EXTRA_ROWS
                   + ([8.5 * mm] * len(_BLANK_SUMMARY) if show_summary else []))
        # repeatRows=0: the column labels (subjects, Score/Grade, S/N, Name) appear
        # only on the first page — when the roster overflows onto further pages the
        # students continue without the header band repeating.
        t = Table(data, colWidths=widths, repeatRows=0, rowHeights=heights)
        style = [
            ('GRID', (0, 0), (-1, -1), 0.9, _BLACK),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('SPAN', (0, 0), (0, 1)),          # S/N spans both header rows
            ('SPAN', (1, 0), (1, 1)),          # Name spans both header rows
            ('TOPPADDING', (0, 0), (-1, -1), 2.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
            ('LEFTPADDING', (2, 0), (-1, -1), 1),    # narrow score/grade columns
            ('RIGHTPADDING', (2, 0), (-1, -1), 1),
        ]
        for j in range(len(group)):           # subject name spans its 2 columns
            c0 = 2 + j * 2
            style.append(('SPAN', (c0, 0), (c0 + 1, 0)))
        if show_summary:                       # one writing box per subject per row
            style.append(('LINEABOVE', (0, sum0), (-1, sum0), 1.3, _BLACK))
            for k in range(len(_BLANK_SUMMARY)):
                for j in range(len(group)):
                    c0 = 2 + j * 2
                    style.append(('SPAN', (c0, sum0 + k), (c0 + 1, sum0 + k)))
        t.setStyle(TableStyle(style))
        e.append(t)

        if _opt(opts, 'grades'):              # WASSCE grade-band reference
            e.append(Spacer(1, 6))
            e.append(_grade_key_table(usable))
        if gi != len(groups) - 1:
            e.append(PageBreak())
    doc.build(e)
    buf.seek(0)
    return buf


def _signature_row(signers):
    """Signature line(s) chosen by the user: both / principal / teacher / none."""
    cols = []
    if signers in ('both', 'teacher'):
        cols.append(Paragraph('_______________________<br/>Class Teacher', _S['cell']))
    if signers in ('both', 'principal'):
        cols.append(Paragraph('_______________________<br/>Principal', _S['cell']))
    if not cols:
        return None
    w = 91 * mm if len(cols) == 2 else 110 * mm
    t = Table([cols], colWidths=[w] * len(cols))
    t.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
    return t


import os as _os
from reportlab.pdfbase import pdfmetrics as _pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont as _TTFont

# Palette + fonts for the designed "Competence Result" slip.
_SL = {
    'NAVY': colors.HexColor('#20304F'), 'GOLD': colors.HexColor('#B8862B'),
    'TAN': colors.HexColor('#D9BC86'), 'INK': colors.HexColor('#22303C'),
    'MUTED': colors.HexColor('#6B7280'), 'LINE': colors.HexColor('#DBE0E8'),
    'PANEL': colors.HexColor('#F6F7F9'), 'ZEBRA': colors.HexColor('#F3F5F8'),
    'STEEL': colors.HexColor('#9AA6BE'), 'RED': colors.HexColor('#B91C1C'),
    'REDBG': colors.HexColor('#F2DADA'), 'WHITE': colors.white,
    'BORDER': colors.HexColor('#111827'),
}
_ICON = {'pin': '', 'phone': '', 'mail': '', 'user': '',
         'mars': '', 'venus': '', 'book': '', 'cert': '',
         'layers': '', 'award': '', 'star': '', 'chart': '',
         'check': '', 'clip': ''}


def _slip_fonts():
    """Register the icon font once; the serif faces are reportlab built-ins."""
    fa = 'Helvetica-Bold'
    try:
        if 'FA' not in _pdfmetrics.getRegisteredFontNames():
            p = _os.path.join(_os.path.dirname(__file__), '..', 'static', 'vendor',
                              'fontawesome', 'webfonts', 'fa-solid-900.ttf')
            _pdfmetrics.registerFont(_TTFont('FA', p))
        fa = 'FA'
    except Exception:
        fa = None
    return {'ser': 'Times-Roman', 'serb': 'Times-Bold', 'seri': 'Times-Italic', 'fa': fa}


def _grade_badge_colors(grade):
    g = (grade or '').upper()
    if g == 'A1':
        return _SL['NAVY'], _SL['WHITE']
    if g in ('B2', 'B3'):
        return _SL['TAN'], _SL['INK']
    if g in ('C4', 'C5', 'C6'):
        return _SL['STEEL'], _SL['WHITE']
    return _SL['REDBG'], _SL['RED']


def _draw_competence_slip(c, PW, PH, student, s, exam, school, opts, signers, F):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    NAVY, GOLD, TAN = _SL['NAVY'], _SL['GOLD'], _SL['TAN']
    INK, MUTED, LINE = _SL['INK'], _SL['MUTED'], _SL['LINE']
    PANEL, ZEBRA, WHITE = _SL['PANEL'], _SL['ZEBRA'], _SL['WHITE']
    ser, serb, seri, fa = F['ser'], F['serb'], F['seri'], F['fa']
    M = 30
    session = exam.session.name if exam.session else ''

    def icon(ch, cx, cy, size, color):
        if not fa or not ch:
            return
        c.setFont(fa, size); c.setFillColor(color)
        c.drawString(cx - stringWidth(ch, fa, size) / 2, cy - size * 0.36, ch)

    def icon_circle(ch, cx, cy, r, glyph_size, ring=LINE, glyph=NAVY):
        c.setStrokeColor(ring); c.setFillColor(WHITE); c.setLineWidth(1)
        c.circle(cx, cy, r, stroke=1, fill=1)
        icon(ch, cx, cy, glyph_size, glyph)

    # outer border
    c.setStrokeColor(_SL['BORDER']); c.setLineWidth(1.4)
    c.roundRect(14, 14, PW - 28, PH - 28, 6, stroke=1, fill=0)

    top = PH - 34
    # ---- Masthead ----------------------------------------------------------
    box_w = 120
    box_x = PW - M - box_w
    logo = (school or {}).get('logo_path')
    name_x = M
    if logo and _os.path.exists(logo):
        try:
            from reportlab.lib.utils import ImageReader
            ir = ImageReader(logo); iw, ih = ir.getSize()
            lh = 74; lw = lh * (iw / ih) if ih else 74
            lw = min(lw, 86)
            c.drawImage(ir, M, top - lh + 4, width=lw, height=lh, mask='auto',
                        preserveAspectRatio=True)
            name_x = M + lw + 14
        except Exception:
            name_x = M
    name = ((school or {}).get('name') or 'School').upper()
    nsize = 30
    name_avail = box_x - 12 - name_x
    while nsize > 15 and stringWidth(name, serb, nsize) > name_avail:
        nsize -= 1
    c.setFillColor(NAVY); c.setFont(serb, nsize)
    c.drawString(name_x, top - 20, name)
    # contact rows
    cy = top - 38
    c.setFont(ser, 10.5)
    addr = (school or {}).get('address') or ''
    if _opt(opts, 'address') and addr:
        icon(_ICON['pin'], name_x + 5, cy + 3.5, 10, NAVY)
        c.setFillColor(INK); c.setFont(ser, 10.5)
        c.drawString(name_x + 15, cy, addr[:70]); cy -= 16
    if _opt(opts, 'contact'):
        phone = (school or {}).get('phone') or ''
        email = (school or {}).get('email') or ''
        x = name_x + 5
        if phone:
            icon(_ICON['phone'], x, cy + 3.5, 9.5, NAVY)
            c.setFillColor(INK); c.setFont(ser, 10.5); c.drawString(x + 12, cy, phone)
            x += 12 + stringWidth(phone, ser, 10.5) + 24
        if email:
            icon(_ICON['mail'], x, cy + 3.5, 9.5, NAVY)
            c.setFillColor(INK); c.setFont(ser, 10.5); c.drawString(x + 13, cy, email)
        cy -= 16
    motto = (school or {}).get('motto') or ''
    if _opt(opts, 'motto') and motto:
        c.setFillColor(GOLD)
        mtext = motto
        mw = stringWidth(mtext, seri, 12)
        mcx = name_x + (name_avail) / 2
        c.setFont(seri, 12); c.setFillColor(colors.HexColor('#4B4B4B'))
        c.drawCentredString(mcx, cy - 2, mtext)
        c.setStrokeColor(GOLD); c.setLineWidth(1)
        c.line(name_x, cy + 2, mcx - mw / 2 - 8, cy + 2)
        c.line(mcx + mw / 2 + 8, cy + 2, box_x - 12, cy + 2)

    # session box
    bx, by, bh = box_x, top - 82, 84
    c.setStrokeColor(LINE); c.setFillColor(colors.HexColor('#FAFBFC')); c.setLineWidth(1)
    c.roundRect(bx, by, box_w, bh, 8, stroke=1, fill=1)
    icon_circle(_ICON['cert'], bx + box_w / 2, by + bh - 20, 14, 15, ring=GOLD, glyph=NAVY)
    c.setFillColor(MUTED); c.setFont(serb, 8.5)
    c.drawCentredString(bx + box_w / 2, by + bh - 44, 'ACADEMIC')
    c.drawCentredString(bx + box_w / 2, by + bh - 54, 'SESSION')
    c.setFillColor(NAVY); c.setFont(serb, 15)
    c.drawCentredString(bx + box_w / 2, by + 16, session or '—')
    c.setStrokeColor(GOLD); c.setLineWidth(1.4)
    c.line(bx + 20, by + 12, bx + box_w - 20, by + 12)

    y = top - 108
    # ---- COMPETENCE RESULT heading ----------------------------------------
    if _opt(opts, 'title'):
        c.setFillColor(NAVY); c.setFont(serb, 26)
        heading = 'COMPETENCE RESULT'
        c.drawCentredString(PW / 2, y - 18, heading)
        hw = stringWidth(heading, serb, 26)
        for sgn in (-1, 1):
            ex = PW / 2 + sgn * (hw / 2 + 18)
            c.setStrokeColor(GOLD); c.setLineWidth(1.2)
            c.line(ex, y - 10, ex + sgn * 40, y - 10)
            c.setFillColor(GOLD)
            c.rect(ex + sgn * 44, y - 13, 5, 5, stroke=0, fill=1)
        y -= 40

    # ---- ribbon banner -----------------------------------------------------
    sub = '%s — Statement of Result' % exam.display_name
    c.setFont(serb, 11.5)
    rw = min(stringWidth(sub, serb, 11.5) + 60, PW - 2 * M)
    rx = PW / 2 - rw / 2; rh2 = 26; ry = y - rh2
    notch = 10
    c.setFillColor(NAVY)
    c.rect(rx, ry, rw, rh2, stroke=0, fill=1)
    p = c.beginPath(); p.moveTo(rx, ry); p.lineTo(rx - notch, ry + rh2 / 2); p.lineTo(rx, ry + rh2); p.close()
    c.drawPath(p, stroke=0, fill=1)
    p = c.beginPath(); p.moveTo(rx + rw, ry); p.lineTo(rx + rw + notch, ry + rh2 / 2); p.lineTo(rx + rw, ry + rh2); p.close()
    c.drawPath(p, stroke=0, fill=1)
    c.setFillColor(WHITE); c.setFont(serb, 11.5)
    c.drawCentredString(PW / 2, ry + 8, sub)
    y = ry - 16

    # ---- student info bar --------------------------------------------------
    bar_h = 52
    c.setStrokeColor(LINE); c.setFillColor(PANEL); c.setLineWidth(1)
    c.roundRect(M, y - bar_h, PW - 2 * M, bar_h, 8, stroke=1, fill=1)
    g = (student.gender or '').lower()
    gi = _ICON['mars'] if g.startswith('m') else (_ICON['venus'] if g.startswith('f') else _ICON['user'])
    cells = [(_ICON['user'], 'Name', student.full_name),
             (gi, 'Gender', student.gender or '—'),
             (_ICON['book'], 'Stream', student.stream or '—')]
    cw = (PW - 2 * M) / 3
    for i, (ic, lab, val) in enumerate(cells):
        cx0 = M + i * cw
        if i:
            c.setStrokeColor(LINE); c.setLineWidth(0.8)
            c.line(cx0, y - bar_h + 10, cx0, y - 10)
        icon_circle(ic, cx0 + 24, y - bar_h / 2, 13, 13, ring=LINE, glyph=NAVY)
        c.setFillColor(MUTED); c.setFont(ser, 9.5)
        c.drawString(cx0 + 44, y - bar_h / 2 + 3, lab + ':')
        c.setFillColor(INK); c.setFont(serb, 12.5)
        c.drawString(cx0 + 44, y - bar_h / 2 - 12, str(val)[:26])
    y -= bar_h + 14

    # ---- results table -----------------------------------------------------
    results = (s or {}).get('results') or []
    cols = [34, PW - 2 * M - 34 - 96 - 92 - 118, 96, 92, 118]  # #, Subject, Score, Grade, Remark
    headers = ['#', 'SUBJECT', 'SCORE (%)', 'GRADE', 'REMARK']
    x0 = M
    hh = 28
    c.setFillColor(NAVY); c.rect(x0, y - hh, sum(cols), hh, stroke=0, fill=1)
    cxp = x0
    c.setFont(serb, 10.5); c.setFillColor(WHITE)
    aligns = ['c', 'l', 'c', 'c', 'c']
    for w, h, al in zip(cols, headers, aligns):
        if al == 'l':
            c.drawString(cxp + 14, y - hh + 9, h)
        else:
            c.drawCentredString(cxp + w / 2, y - hh + 9, h)
        cxp += w
    yy = y - hh
    n = max(1, len(results))
    rh = min(34, max(20, (yy - 150) / n))   # keep room for the summary below
    for i, r in enumerate(results, 1):
        if i % 2 == 0:
            c.setFillColor(ZEBRA); c.rect(x0, yy - rh, sum(cols), rh, stroke=0, fill=1)
        mid = yy - rh / 2
        c.setFillColor(INK); c.setFont(serb, 11)
        c.drawCentredString(x0 + cols[0] / 2, mid - 4, str(i))
        c.setFont(ser, 11)
        c.drawString(x0 + cols[0] + 14, mid - 4, str(r.subject)[:34])
        c.drawCentredString(x0 + cols[0] + cols[1] + cols[2] / 2, mid - 4,
                            '' if r.score is None else str(r.score))
        # grade badge
        bgc, fgc = _grade_badge_colors(r.grade)
        bw2 = 40; bh2 = 20
        bcx = x0 + cols[0] + cols[1] + cols[2] + cols[3] / 2
        c.setFillColor(bgc)
        c.roundRect(bcx - bw2 / 2, mid - bh2 / 2, bw2, bh2, 4, stroke=0, fill=1)
        c.setFillColor(fgc); c.setFont(serb, 10.5)
        c.drawCentredString(bcx, mid - 4, (r.grade or '—'))
        # remark
        rk = 'Credit' if r.is_pass else 'Fail'
        c.setFillColor(INK if r.is_pass else _SL['RED']); c.setFont(ser, 11)
        c.drawCentredString(x0 + cols[0] + cols[1] + cols[2] + cols[3] + cols[4] / 2, mid - 4, rk)
        c.setStrokeColor(LINE); c.setLineWidth(0.6)
        c.line(x0, yy - rh, x0 + sum(cols), yy - rh)
        yy -= rh
    if not results:
        c.setFillColor(MUTED); c.setFont(seri, 11)
        c.drawCentredString(PW / 2, yy - 24, 'No results recorded for this student.')
        yy -= 44
    c.setStrokeColor(NAVY); c.setLineWidth(1)
    c.rect(x0, yy, sum(cols), (y - hh) - yy, stroke=1, fill=0)
    c.rect(x0, y - hh, sum(cols), hh, stroke=1, fill=0)
    y = yy - 14

    # ---- summary panel -----------------------------------------------------
    if _opt(opts, 'summary') and s:
        core = ', '.join(s.get('missing_core') or []) or 'None'
        avg = s.get('average_score')
        rows = [
            (_ICON['layers'], 'Subjects:', str(s.get('subjects', 0)),
             _ICON['award'], 'Credits (C6+):', str(s.get('credits', 0))),
            (_ICON['star'], 'Distinctions (A1–B3):', str(s.get('distinctions', 0)),
             _ICON['chart'], 'Average:', ('%s%%' % avg if avg is not None else '—')),
            (_ICON['check'], '5 credits incl. English & Maths:',
             'YES' if s.get('has_5_incl_core') else 'NO',
             _ICON['clip'], 'Missing core:', core),
        ]
        ph = 30 * len(rows) + 16
        c.setStrokeColor(LINE); c.setFillColor(PANEL); c.setLineWidth(1)
        c.roundRect(M, y - ph, PW - 2 * M, ph, 8, stroke=1, fill=1)
        colw = (PW - 2 * M) / 2
        ry2 = y - 8
        for r in rows:
            for half in (0, 1):
                ic, lab, val = r[half * 3], r[half * 3 + 1], r[half * 3 + 2]
                cx0 = M + half * colw + 12
                midy = ry2 - 15
                icon_circle(ic, cx0 + 11, midy, 11, 11, ring=LINE, glyph=NAVY)
                c.setFillColor(MUTED); c.setFont(ser, 10)
                c.drawString(cx0 + 28, midy + 3.5, lab)
                c.setFillColor(NAVY); c.setFont(serb, 12)
                vx = M + half * colw + colw - 16
                c.drawRightString(vx, midy - 4, str(val)[:22])
                # dotted leader
                lab_end = cx0 + 28 + stringWidth(lab, ser, 10) + 6
                val_w = stringWidth(str(val)[:22], serb, 12)
                c.setDash(1, 2); c.setStrokeColor(LINE); c.setLineWidth(0.6)
                if vx - val_w - 6 > lab_end:
                    c.line(lab_end, midy - 1, vx - val_w - 6, midy - 1)
                c.setDash()
            ry2 -= 30
        y -= ph + 16

    # ---- signatures --------------------------------------------------------
    if signers in ('both', 'teacher', 'principal'):
        labels = []
        if signers in ('both', 'teacher'):
            labels.append('Class Teacher')
        if signers in ('both', 'principal'):
            labels.append('Principal')
        sy = max(y, 96)
        seg = (PW - 2 * M) / len(labels)
        for i, lab in enumerate(labels):
            lcx = M + seg * i + seg / 2
            c.setStrokeColor(INK); c.setLineWidth(0.8)
            c.line(lcx - 70, sy, lcx + 70, sy)
            c.setFillColor(INK); c.setFont(ser, 10.5)
            c.drawCentredString(lcx, sy - 14, lab)
            c.setFillColor(MUTED); c.setFont(ser, 9.5)
            c.drawString(lcx - 70, sy - 30, 'Date: ')
            c.setStrokeColor(LINE); c.setLineWidth(0.7)
            c.line(lcx - 42, sy - 30, lcx + 70, sy - 30)

    # ---- footer ------------------------------------------------------------
    c.setStrokeColor(_SL['BORDER']); c.setLineWidth(0.8)
    c.line(M, 40, PW - M, 40)
    c.setFillColor(GOLD); c.setFont(serb, 9)
    tail = 'Thank you for choosing %s' % ((school or {}).get('name') or 'our school')
    c.setFillColor(colors.HexColor('#4B4B4B')); c.setFont(seri, 10)
    tw = stringWidth(tail, seri, 10)
    c.drawCentredString(PW / 2, 27, tail)
    c.setFillColor(GOLD)
    for sgn in (-1, 1):
        c.circle(PW / 2 + sgn * (tw / 2 + 12), 30.5, 1.6, stroke=0, fill=1)


def result_slips_pdf(slips, exam, school, opts=None, signers='both'):
    """One A4 designed "Competence Result" statement per student. ``opts`` toggles
    the identity/banner/summary blocks; ``signers`` chooses the signature line(s)."""
    from reportlab.pdfgen import canvas as _canvas
    F = _slip_fonts()
    buf = io.BytesIO()
    PW, PH = A4
    c = _canvas.Canvas(buf, pagesize=A4)
    c.setTitle('Results — %s' % exam.display_name)
    if not slips:
        c.setFont('Times-Roman', 12)
        c.drawCentredString(PW / 2, PH / 2, 'No results to print.')
        c.showPage(); c.save(); buf.seek(0)
        return buf
    for slip in slips:
        _draw_competence_slip(c, PW, PH, slip['student'], slip['summary'],
                              exam, school, opts, signers, F)
        c.showPage()
    c.save(); buf.seek(0)
    return buf
