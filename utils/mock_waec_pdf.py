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


def _broadsheet(exam, school, opts, subjects, rows, subject_summary, per, orient,
                *, blank, offered=None, min_w=13 * mm, row_h=None, title_word='Broadsheet'):
    """Shared broadsheet renderer. The filled sheet and the blank recording sheet
    are the **same** table — identical columns (S/N, Name, one column per subject
    with a vertical header, then Credits and Average %), the same extra rows and
    the same summary rows — the only difference is whether the score/grade and
    summary cells carry values (filled) or are left empty to write into (blank).

    ``rows`` is a list of {student, cells, credits, average_score}; for the blank
    sheet ``cells`` is ignored and ``offered`` (student.id -> set of subjects)
    shades the columns a student does not sit. ``subject_summary`` carries the
    per-subject tallies for the filled sheet (None/empty cells when blank)."""
    _styles()
    page = _pagesize(orient)
    buf = io.BytesIO()
    label = 'Blank broadsheet' if blank else 'Broadsheet'
    doc = SimpleDocTemplate(buf, pagesize=page, topMargin=8 * mm,
                            bottomMargin=8 * mm, leftMargin=8 * mm, rightMargin=8 * mm,
                            title=f'{label} — {exam.display_name}')
    usable = page[0] - 16 * mm
    sn_w, name_w = 9 * mm, 52 * mm
    # Vertical headers don't constrain width; reserve room for the two tail
    # columns (Credits, Average %) and keep each subject column writable.
    per = _fit_per(usable, sn_w, name_w, 24 * mm, min_w, per, len(subjects))
    groups = _groups(subjects, per)
    nrows = len(rows)
    show_summary = _opt(opts, 'summary')
    e = []
    for gi, group in enumerate(groups):
        last = gi == len(groups) - 1
        sub = f'{exam.display_name} — {title_word}'
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
        shaded = []
        for i, row in enumerate(rows, 1):
            line = [str(i), Paragraph(row['student'].full_name, _S['name'])]
            take = (offered.get(row['student'].id) if offered else None) or set()
            for ci, s in enumerate(group):
                if blank:
                    line.append('')
                    if take and s not in take:
                        shaded.append((2 + ci, i))           # data row i (header is row 0)
                else:
                    r = row['cells'].get(s)
                    line.append(f'{r.score} {r.grade}' if (r and r.score is not None) else '')
            if last:
                if blank:
                    line += ['', '']
                else:
                    line += [str(row['credits']),
                             (str(row['average_score']) if row['average_score'] is not None else '')]
            data.append(line)

        ncols = 2 + len(group) + tail
        for _ in range(_EXTRA_ROWS):                          # blank rows for additions
            data.append([''] * ncols)

        sum0 = nrows + 1 + _EXTRA_ROWS                        # first summary row index
        if show_summary:
            if blank:
                for label_txt in _BLANK_SUMMARY:
                    rr = ['', Paragraph(label_txt, _S['name'])] + [''] * len(group)
                    if last:
                        rr += ['', '']
                    data.append(rr)
            else:
                ss = subject_summary
                for label_txt, fn in (('No. offered', lambda d: d['offered']),
                                      ('No. passed (C6+)', lambda d: d['passed']),
                                      ('No. failed', lambda d: d['failed']),
                                      ('Average score %', lambda d: d['avg_score'] if d['avg_score'] is not None else '—'),
                                      ('Average grade', lambda d: d['avg_grade'])):
                    rr = ['', label_txt] + [str(fn(ss[s])) for s in group]
                    if last:
                        rr += ['', '']
                    data.append(rr)

        widths = [sn_w, name_w] + [sub_w] * (len(group) + tail)
        data_h = row_h if row_h is not None else None
        heights = ([None] + [data_h] * nrows + [7.5 * mm] * _EXTRA_ROWS
                   + ([data_h] * len(_BLANK_SUMMARY) if show_summary else []))
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
        for col, rw in shaded:                                # shade non-offered subjects
            style.append(('BACKGROUND', (col, rw), (col, rw), _SHADE))
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


def broadsheet_pdf(bs, exam, school, opts=None, per=8, orient='landscape'):
    """Full score+grade matrix. Wide subject sets split across pages (``per``
    columns each); no admission numbers. ``opts['summary']`` toggles the
    per-subject offered/passed/failed/average rows. ``orient`` is landscape or
    portrait A4, filling the page with an 8mm margin."""
    return _broadsheet(exam, school, opts, bs['subjects'], bs['rows'],
                       bs['subject_summary'], per, orient, blank=False,
                       min_w=13 * mm, title_word='Broadsheet')


def blank_broadsheet_pdf(students, offered, subjects, exam, school, opts=None,
                         per=8, orient='landscape'):
    """A blank recording sheet — identical in layout to the filled broadsheet
    (same S/N, Name, one vertical-headed column per subject, then Credits and
    Average %, plus the same summary rows), only with the cells left empty to
    write into. Subjects a student does not offer are shaded out."""
    rows = [{'student': st, 'cells': {}, 'credits': '', 'average_score': None}
            for st in students]
    return _broadsheet(exam, school, opts, subjects, rows, None, per, orient,
                       blank=True, offered=offered, min_w=15 * mm, row_h=8.5 * mm,
                       title_word='Recording Sheet')


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
