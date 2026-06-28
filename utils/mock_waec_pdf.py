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
    _S['subhead'] = ParagraphStyle('sh', parent=base['Normal'], fontSize=6.5, leading=7,
                                   alignment=TA_CENTER, fontName='Helvetica-Bold')
    _S['name'] = ParagraphStyle('nm', parent=base['Normal'], fontSize=8.5, leading=9.5,
                                fontName='Helvetica-Bold')
    _S['cell'] = ParagraphStyle('c', parent=base['Normal'], fontSize=10)
    return _S


def _opt(opts, key, default=True):
    return default if opts is None else opts.get(key, default)


def _school_header(e, school, opts, subtitle):
    """School identity block + optional COMPETENCE RESULT banner + a subtitle."""
    _styles()
    if school.get('name'):
        e.append(Paragraph((school['name'] or '').upper(), _S['school']))
    if _opt(opts, 'address') and school.get('address'):
        e.append(Paragraph(school['address'], _S['addr']))
    if _opt(opts, 'contact'):
        contact = ' · '.join(x for x in (school.get('phone'), school.get('email')) if x)
        if contact:
            e.append(Paragraph(contact, _S['addr']))
    if _opt(opts, 'motto') and school.get('motto'):
        e.append(Paragraph('<i>%s</i>' % school['motto'], _S['addr']))
    if _opt(opts, 'title'):
        e.append(Paragraph('COMPETENCE RESULT', _S['comp']))
    if subtitle:
        e.append(Paragraph(subtitle, _S['exam']))


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
        ('BACKGROUND', (0, 0), (0, -1), _HEAD),
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
            line = [str(i), Paragraph(row['student'].full_name, _S['name'])]
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
        t = Table(data, colWidths=widths, repeatRows=1, rowHeights=heights)
        style = [
            ('GRID', (0, 0), (-1, -1), 0.9, _BLACK),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, nrows), 9.5),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('VALIGN', (0, 0), (-1, 0), 'BOTTOM'),
            ('BACKGROUND', (0, 0), (-1, 0), _HEAD),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ]
        if show_summary:
            style.append(('FONTSIZE', (0, sum0), (-1, -1), 8.5))
            style.append(('BACKGROUND', (0, sum0), (-1, -1), _FOOT))
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
    """A blank recording sheet: student names down the side, every offered subject
    across the top with its own **Score** and **Grade** columns to write into.
    Subjects a student does not offer are shaded out. Landscape or portrait A4.

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
    sn_w, name_w = 8 * mm, 46 * mm
    # Two writable columns (Score + Grade) per subject. Reserve only ~13mm per
    # subject so the full WAEC set fits one landscape sheet; columns narrow before
    # the sheet splits. (~6.5mm per Score/Grade column at the full load.)
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
            h2 += [Paragraph('Sc', _S['subhead']), Paragraph('Gr', _S['subhead'])]
        data = [h1, h2]
        shaded = []
        for i, st in enumerate(students, 1):
            line = [str(i), Paragraph(st.full_name, _S['name'])]
            take = offered.get(st.id) or set()
            for ci, s in enumerate(group):
                line += ['', '']
                if take and s not in take:
                    shaded.append((2 + ci * 2, 1 + i))      # row index incl. 2 header rows
            data.append(line)

        for _ in range(_EXTRA_ROWS):                        # blank rows for additions
            data.append(['', ''] + [''] * (2 * len(group)))

        # Blank summary rows for filling the per-subject tallies by hand.
        show_summary = _opt(opts, 'summary')
        sum0 = len(data)                        # table row of the first summary row
        if show_summary:
            for label in _BLANK_SUMMARY:
                data.append(['', Paragraph(label, _S['name'])] + [''] * (2 * len(group)))

        widths = [sn_w, name_w] + [cell_w] * (2 * len(group))
        heights = ([None, None] + [8.5 * mm] * nstud + [8.5 * mm] * _EXTRA_ROWS
                   + ([8.5 * mm] * len(_BLANK_SUMMARY) if show_summary else []))
        t = Table(data, colWidths=widths, repeatRows=2, rowHeights=heights)
        style = [
            ('GRID', (0, 0), (-1, -1), 0.9, _BLACK),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, 1), _HEAD),
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
        for col, rw in shaded:                 # shade Score+Grade of non-offered
            style.append(('BACKGROUND', (col, rw), (col + 1, rw), _SHADE))
        if show_summary:                       # one writing box per subject per row
            style.append(('LINEABOVE', (0, sum0), (-1, sum0), 1.3, _BLACK))
            style.append(('BACKGROUND', (0, sum0), (1, sum0 + len(_BLANK_SUMMARY) - 1), _FOOT))
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


def result_slips_pdf(slips, exam, school, opts=None, signers='both'):
    """One A4 "Statement of Result" per student. ``opts`` toggles the summary box
    and the shared school-identity / banner blocks; ``signers`` chooses which
    signature line(s) appear (both / principal / teacher / none)."""
    _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=12 * mm, bottomMargin=12 * mm,
                            leftMargin=14 * mm, rightMargin=14 * mm,
                            title=f'Results — {exam.display_name}')
    e = []
    session = exam.session.name if exam.session else ''
    show_summary = _opt(opts, 'summary')
    for idx, slip in enumerate(slips):
        student, s = slip['student'], slip['summary']
        sub = f'{exam.display_name} — Statement of Result'
        if session:
            sub += f' · {session}'
        _school_header(e, school, opts, sub)

        meta = [
            [Paragraph(f'<b>Name:</b> {student.full_name}', _S['cell']),
             Paragraph(f"<b>Stream:</b> {student.stream or '—'}", _S['cell'])],
            [Paragraph(f'<b>Gender:</b> {student.gender or "—"}', _S['cell']),
             Paragraph('', _S['cell'])],
        ]
        mt = Table(meta, colWidths=[95 * mm, 87 * mm])
        mt.setStyle(TableStyle([('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
        e.append(mt)
        e.append(Spacer(1, 4))

        if s and s.get('results'):
            data = [['#', 'Subject', 'Score', 'Grade', 'Remark']]
            for i, r in enumerate(s['results'], 1):
                data.append([str(i), r.subject,
                             '' if r.score is None else str(r.score),
                             r.grade or '—', 'Credit' if r.is_pass else 'Fail'])
            t = Table(data, colWidths=[10 * mm, 92 * mm, 24 * mm, 24 * mm, 32 * mm], repeatRows=1)
            t.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.7, _BLACK),
                ('BACKGROUND', (0, 0), (-1, 0), _HEAD),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (3, 1), (3, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9.5),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            for ri, r in enumerate(s['results'], 1):
                t.setStyle(TableStyle([('TEXTCOLOR', (4, ri), (4, ri),
                    colors.HexColor('#047857') if r.is_pass else colors.HexColor('#b91c1c'))]))
            e.append(t)
            e.append(Spacer(1, 6))

            if show_summary:
                core = ', '.join(s.get('missing_core') or []) or 'None'
                summ = [
                    [Paragraph(f"<b>Subjects:</b> {s['subjects']}", _S['cell']),
                     Paragraph(f"<b>Credits (C6+):</b> {s['credits']}", _S['cell'])],
                    [Paragraph(f"<b>Distinctions (A1–B3):</b> {s['distinctions']}", _S['cell']),
                     Paragraph(f"<b>Average:</b> {s['average_score'] if s['average_score'] is not None else '—'}%", _S['cell'])],
                    [Paragraph(f"<b>5 credits incl. English &amp; Maths:</b> {'YES' if s['has_5_incl_core'] else 'NO'}", _S['cell']),
                     Paragraph(f"<b>Missing core:</b> {core}", _S['cell'])],
                ]
                stbl = Table(summ, colWidths=[95 * mm, 87 * mm])
                stbl.setStyle(TableStyle([
                    ('BOX', (0, 0), (-1, -1), 0.7, _BLACK),
                    ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#cccccc')),
                    ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ]))
                e.append(stbl)
        else:
            e.append(Paragraph('No results recorded for this student.', _S['cell']))

        sign = _signature_row(signers)
        if sign is not None:
            e.append(Spacer(1, 22))
            e.append(sign)
        if idx != len(slips) - 1:
            e.append(PageBreak())
    if not slips:
        e.append(Paragraph('No results to print.', _S['cell']))
    doc.build(e)
    buf.seek(0)
    return buf
