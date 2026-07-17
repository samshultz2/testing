"""Server-side PDF rendering of a student's term report card (reportlab).

Two-column terminal report-sheet layout: the student particulars and the
subject/score table on the left, with an affective-domain table, grade key and
teacher/principal remarks in a right sidebar. Monochrome apart from the school
logo, so it prints cleanly. Driven by the same build_report_card data as the
on-screen sheet.
"""
import io
from xml.sax.saxutils import escape as _xml_escape

from utils.numfmt import fmt_num as _n

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                Spacer, PageBreak, Flowable, KeepInFrame)
from reportlab.pdfbase.pdfmetrics import stringWidth

_INK = colors.black
_GRID = colors.HexColor('#333333')

# How tall the subject rows may grow to fill the page (mm) and the target height
# the subject table aims for. Tuned so a typical sheet fills most of the page.
_MAXROW_MM = 10.5
_TARGET_MM = 175.0


def _esc(v):
    """Escape a value before it is placed into reportlab Paragraph mini-XML markup."""
    return _xml_escape('' if v is None else str(v))


_S = {}


def _styles():
    if _S:
        return _S
    base = getSampleStyleSheet()
    _S['title'] = ParagraphStyle('t', parent=base['Title'], fontSize=18, textColor=_INK, spaceAfter=1)
    _S['school_line'] = ParagraphStyle('sl', parent=base['Normal'], alignment=TA_CENTER,
                                       fontSize=10, leading=12.5, textColor=_INK)
    _S['motto'] = ParagraphStyle('mt', parent=base['Normal'], alignment=TA_CENTER, fontSize=9.5,
                                 leading=11, textColor=colors.HexColor('#333333'), fontName='Helvetica-Oblique')
    _S['sheet'] = ParagraphStyle('sh', parent=base['Normal'], alignment=TA_CENTER, fontSize=12.5,
                                 leading=14, fontName='Helvetica-Bold', textColor=_INK)
    _S['lbl'] = ParagraphStyle('lb', parent=base['Normal'], fontSize=9.5, leading=11.5)
    _S['subj'] = ParagraphStyle('sj', parent=base['Normal'], fontSize=9, leading=10.5)
    _S['rmk'] = ParagraphStyle('rk', parent=base['Normal'], fontSize=8, leading=9)
    _S['sidehdr'] = ParagraphStyle('sd', parent=base['Normal'], fontSize=10, leading=11.5,
                                   fontName='Helvetica-Bold', alignment=TA_CENTER, textColor=_INK)
    _S['side'] = ParagraphStyle('si', parent=base['Normal'], fontSize=8.5, leading=10)
    _S['remark'] = ParagraphStyle('rm', parent=base['Normal'], fontSize=8.5, leading=10.5)
    _S['sub'] = ParagraphStyle('s', parent=base['Normal'], alignment=TA_CENTER, fontSize=10)
    return _S


def _school_dict(school):
    """Accept either a school-profile dict or a bare name string (back-compat)."""
    if isinstance(school, dict):
        return school
    return {'name': school or 'School', 'address': '', 'phone': '', 'email': '',
            'motto': '', 'logo_path': None}


class _VText(Flowable):
    """A short header label drawn rotated 90° (bottom-to-top), for narrow columns."""
    def __init__(self, text, size=8, pad=4):
        Flowable.__init__(self)
        self.text = '' if text is None else str(text)
        self.size = size
        self.width = size + 1.5
        self.height = stringWidth(self.text, 'Helvetica-Bold', size) + pad * 2

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFont('Helvetica-Bold', self.size)
        c.translate(self.width, 3)
        c.rotate(90)
        c.drawString(0, -self.size + 1.5, self.text)
        c.restoreState()


def _sheet_level(name):
    up = (name or '').upper()
    if 'SS' in up or 'SENIOR' in up:
        return 'Senior Secondary School'
    if 'JS' in up or 'JUNIOR' in up:
        return 'Junior Secondary School'
    if 'PRY' in up or 'PRIMARY' in up or 'BASIC' in up:
        return 'Primary School'
    return ''


# --------------------------------------------------------------------------- #
# Left column: particulars box, subject table, summary block
# --------------------------------------------------------------------------- #

def _particulars(student, report_data, term, width):
    s = _styles()
    level = _sheet_level(report_data['assignment'].display_name)
    title = (f'{level} Report Sheet' if level else 'Terminal Report Sheet')
    pos = report_data.get('term_summary')
    pos = pos.position_in_class if (pos and pos.position_in_class) else '—'
    ap = report_data.get('attendance_present')
    if ap is not None:
        att = _n(ap)
        if report_data.get('attendance_days_opened'):
            att += f" / {_n(report_data['attendance_days_opened'] * 2)}"
        if report_data.get('attendance_pct') is not None:
            att += f" ({_n(report_data['attendance_pct'])}%)"
    else:
        att = '—'

    def pair(label, value):
        return Paragraph(f'<b>{_esc(label)}:</b> {_esc(value)}', s['lbl'])

    rows = [[Paragraph(title, s['sheet']), '', '', '']]
    body = [
        ('NAME', student.full_name, 'TERM', term.name),
        ('CLASS', report_data['assignment'].display_name, 'SESSION', term.session.name if term.session else ''),
        ('EXAM NO', student.student_id, 'NO. IN CLASS', report_data.get('no_in_class', '—')),
        ('ATTENDANCE', att, '', ''),
    ]
    for l1, v1, l2, v2 in body:
        rows.append([pair(l1, v1), '', pair(l2, v2) if l2 else '', ''])
    lw = width * 0.30
    t = Table(rows, colWidths=[lw, width * 0.20, lw, width * 0.20])
    t.setStyle(TableStyle([
        ('SPAN', (0, 0), (-1, 0)),
        ('SPAN', (0, 1), (1, 1)), ('SPAN', (2, 1), (3, 1)),
        ('SPAN', (0, 2), (1, 2)), ('SPAN', (2, 2), (3, 2)),
        ('SPAN', (0, 3), (1, 3)), ('SPAN', (2, 3), (3, 3)),
        ('SPAN', (0, 4), (3, 4)),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('BOX', (0, 0), (-1, -1), 0.8, _INK),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, _INK),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
    ]))
    return t


def _subject_table(report_data, width):
    s = _styles()
    cols = report_data.get('columns') or [{'key': a.id, 'label': (a.short_name or a.name)}
                                          for a in report_data['assessment_types']]
    n = len(cols)
    # column widths
    total_w, grade_w, remark_w = 11 * mm, 9 * mm, 22 * mm
    assess_w = max(6 * mm, min(9 * mm, (width - 40 * mm - total_w - grade_w - remark_w) / max(n, 1)))
    subj_w = width - (assess_w * n + total_w + grade_w + remark_w)
    col_widths = [subj_w] + [assess_w] * n + [total_w, grade_w, remark_w]

    head = [Paragraph('<b>SUBJECTS</b>', s['subj'])]
    head += [_VText(c['label']) for c in cols]
    head += [_VText('TOTAL'), _VText('GRADE'), _VText('REMARK')]
    data = [head]
    for row in report_data['subjects']:
        rc = row.get('cells')
        if rc is None:
            rc = [row['assessments'].get(c['key']) for c in cols]
        line = [Paragraph(_esc(row['subject'].name), s['subj'])]
        line += [_n(v, blank='') for v in rc]
        line += [_n(row['total']), row['grade'], Paragraph(_esc(row['remark']), s['rmk'])]
        data.append(line)

    # header height from the longest rotated label
    labels = [c['label'] for c in cols] + ['TOTAL', 'GRADE', 'REMARK']
    hh = min(34 * mm, max(15 * mm, max((stringWidth(x, 'Helvetica-Bold', 8) for x in labels), default=0) + 6 * mm))
    # Taller body rows so the sheet fills the page for shorter subject lists;
    # KeepInFrame shrinks the whole card to fit when the list is long.
    nrows = len(data) - 1
    body_h = max(8 * mm, min(_MAXROW_MM * mm, (_TARGET_MM * mm - hh) / nrows)) if nrows else 10 * mm
    heights = [hh] + [body_h] * nrows
    t = Table(data, colWidths=col_widths, rowHeights=heights, repeatRows=1)
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, 0), 'BOTTOM'),
        ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, _GRID),
        ('TOPPADDING', (0, 1), (-1, -1), 3), ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (0, -1), 4),
    ]))
    return t


def _summary_block(report_data, width):
    s = _styles()

    def pair(label, value):
        return Paragraph(f'<b>{_esc(label)}:</b> {_esc(value)}', s['lbl'])

    pos = report_data.get('term_summary')
    pos = pos.position_in_class if (pos and pos.position_in_class) else '—'
    rows = [
        (pair('No. of Subjects', report_data['total_subjects']), pair('Class Position', pos)),
        (pair('Scores Obtainable', _n(report_data.get('scores_obtainable'), blank='—')),
         pair('Average Mark', f"{_n(report_data.get('average_pct', report_data['average']))}%")),
        (pair('Score Obtained', _n(report_data['total_score'])),
         pair('Result Status', report_data.get('result_status', ''))),
        (pair('Next Term Fees', report_data.get('next_term_fees') or '—'),
         pair('Next Term Begins', report_data.get('next_term_begins') or '—')),
    ]
    t = Table([[a, b] for a, b in rows], colWidths=[width * 0.5, width * 0.5])
    t.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.8, _INK),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#bbbbbb')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
    ]))
    return t


# --------------------------------------------------------------------------- #
# Right sidebar: affective domain, grade key, remarks
# --------------------------------------------------------------------------- #

def _sidebar(report_data, affective_traits, rating_labels, width):
    s = _styles()
    flows = []
    ts = report_data.get('term_summary')
    aff = ts.affective_map if ts else {}

    # Affective domain — every configured trait, with its rating (blank if unset).
    adata = [[Paragraph('AFFECTIVE DOMAIN', s['sidehdr']), '']]
    for k, label in (affective_traits or []):
        r = aff.get(k)
        adata.append([Paragraph(_esc(label), s['side']),
                      Paragraph(f'{_n(r)}/5' if r else '', s['side'])])
    if len(adata) == 1:
        adata.append([Paragraph('Not assessed', s['side']), ''])
    at = Table(adata, colWidths=[width * 0.68, width * 0.32])
    at.setStyle(TableStyle([
        ('SPAN', (0, 0), (1, 0)),
        ('ALIGN', (1, 1), (1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.4, _GRID),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
    ]))
    flows.append(at)
    flows.append(Spacer(1, 5))

    # Grade key.
    if report_data.get('grade_scale'):
        gdata = [[Paragraph('GRADE KEY', s['sidehdr']), '']]
        for b in report_data['grade_scale']:
            gdata.append([Paragraph(f'{_esc(b.grade)}', s['side']),
                          Paragraph(f'{_n(b.min_score)}–{_n(b.max_score)}'
                                    + (f' · {_esc(b.remark)}' if b.remark else ''), s['side'])])
        gt = Table(gdata, colWidths=[width * 0.28, width * 0.72])
        gt.setStyle(TableStyle([
            ('SPAN', (0, 0), (1, 0)),
            ('GRID', (0, 0), (-1, -1), 0.4, _GRID),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ]))
        flows.append(gt)
        flows.append(Spacer(1, 5))

    # Remarks + signatures.
    tc = (ts.teacher_comment if ts else '') or ''
    pc = (ts.principal_comment if ts else '') or ''
    rdata = [
        [Paragraph('REMARKS', s['sidehdr'])],
        [Paragraph("<b>Class Teacher's Remark:</b>", s['side'])],
        [Paragraph(_esc(tc) or '&nbsp;', s['remark'])],
        [Paragraph('Signature: ______________', s['side'])],
        [Paragraph("<b>Principal's Remark:</b>", s['side'])],
        [Paragraph(_esc(pc) or '&nbsp;', s['remark'])],
        [Paragraph('Signature: ______________', s['side'])],
    ]
    rt = Table(rdata, colWidths=[width])
    rt.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('BOX', (0, 0), (-1, -1), 0.4, _GRID),
        ('LINEBELOW', (0, 0), (-1, 0), 0.6, _INK),
        ('LINEBELOW', (0, 2), (-1, 2), 0.3, colors.HexColor('#bbbbbb')),
        ('LINEBELOW', (0, 5), (-1, 5), 0.3, colors.HexColor('#bbbbbb')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
    ]))
    flows.append(rt)
    return flows


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #

def _card_flowables(student, report_data, term, school, affective_traits, rating_labels,
                    frame_w=190 * mm):
    """Flowables for one student's two-column report sheet."""
    s = _styles()
    from utils.school import logo_flowable, logo_header_flowable
    sch = _school_dict(school)
    e = []

    # Letterhead — logo (the only colour) beside the centred name + contact lines.
    logo = logo_flowable(max_h_mm=18, max_w_mm=30, path=sch.get('logo_path'))
    name = sch.get('name') or 'School'
    items = [(Paragraph(_esc(name), s['title']), name, 'Helvetica-Bold', 16)]
    if sch.get('address'):
        items.append((Paragraph(_esc(sch['address']), s['school_line']), sch['address'], 'Helvetica', 9))
    contact = ' · '.join(x for x in [
        (f"Tel: {sch['phone']}" if sch.get('phone') else ''), sch.get('email') or ''] if x)
    if contact:
        items.append((Paragraph(_esc(contact), s['school_line']), contact, 'Helvetica', 9))
    if sch.get('motto'):
        items.append((Paragraph(_esc(sch['motto']), s['motto']), sch['motto'], 'Helvetica-Oblique', 8.5))
    header = logo_header_flowable(logo, items) if logo is not None else None
    if header is not None:
        e.append(header)
    else:
        e.extend(it[0] for it in items)
    e.append(Spacer(1, 5))

    # Two columns.
    gap = 5 * mm
    left_w = frame_w * 0.66
    right_w = frame_w - left_w - gap
    left = [_particulars(student, report_data, term, left_w), Spacer(1, 5),
            _subject_table(report_data, left_w), Spacer(1, 5),
            _summary_block(report_data, left_w)]
    right = _sidebar(report_data, affective_traits, rating_labels, right_w)
    body = Table([[left, right]], colWidths=[left_w, gap + right_w])
    body.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0), ('RIGHTPADDING', (0, 0), (0, 0), gap),
        ('LEFTPADDING', (1, 0), (1, 0), 0), ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    e.append(body)
    return e


def _card_page(doc, student, report_data, term, school, affective_traits, rating_labels):
    """A single report card wrapped so the whole sheet — letterhead + body —
    always fits on exactly one page (KeepInFrame shrinks it if it's too tall)."""
    flows = _card_flowables(student, report_data, term, school, affective_traits,
                            rating_labels, frame_w=doc.width)
    return KeepInFrame(doc.width, doc.height, flows, mode='shrink', hAlign='CENTER')


def report_card_pdf(student, report_data, term, school, affective_traits, rating_labels):
    """A single student's report sheet as a one-PDF buffer. ``school`` may be the
    full school-profile dict (name/address/phone/email/motto/logo) or a name str."""
    _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=10 * mm, bottomMargin=10 * mm,
                            leftMargin=10 * mm, rightMargin=10 * mm,
                            title=f'Report — {student.full_name}')
    doc.build([_card_page(doc, student, report_data, term, school, affective_traits, rating_labels)])
    buf.seek(0)
    return buf


def batch_report_cards_pdf(cards, school, affective_traits, rating_labels, *, title='Report Cards'):
    """A whole class's report sheets in one PDF, one student per page."""
    _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=10 * mm, bottomMargin=10 * mm,
                            leftMargin=10 * mm, rightMargin=10 * mm, title=title)
    flow = []
    first = True
    for (student, report_data, term) in cards:
        if not report_data:
            continue
        if not first:
            flow.append(PageBreak())
        first = False
        flow.append(_card_page(doc, student, report_data, term, school,
                               affective_traits, rating_labels))
    if not flow:
        flow.append(Paragraph('No results to export.', _S['sub']))
    doc.build(flow)
    buf.seek(0)
    return buf
