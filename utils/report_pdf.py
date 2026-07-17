"""Server-side PDF rendering of a student's term report card (reportlab).

Mirrors templates/subjects/report_card.html from the same build_report_card data,
so the downloaded PDF matches the on-screen / printed sheet.
"""
import io
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                Spacer, PageBreak)

# Monochrome report card — the school logo is the only splash of colour. Headings
# and table chrome are black / grey so it prints cleanly on any printer.
_PRIMARY = colors.black
_LIGHT = colors.HexColor('#f0f0f0')          # neutral grey zebra (grayscale)


def _esc(v):
    """Escape a value before it is placed into reportlab Paragraph mini-XML markup,
    so a name/comment containing '<', '&' or '>' can't corrupt or inject the PDF
    layout (reportlab runs no JS — this is markup-injection hardening)."""
    return _xml_escape('' if v is None else str(v))


def _info_table(pairs, col_widths):
    rows = [[Paragraph(f'<b>{_esc(k)}:</b> {_esc(v)}', _S['cell']) for k, v in chunk]
            for chunk in pairs]
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    return t


_S = {}


def _styles():
    if _S:
        return _S
    base = getSampleStyleSheet()
    _S['title'] = ParagraphStyle('t', parent=base['Title'], fontSize=16,
                                 textColor=_PRIMARY, spaceAfter=1)
    _S['school_line'] = ParagraphStyle('sl', parent=base['Normal'], alignment=TA_CENTER,
                                       fontSize=9, leading=11, textColor=colors.black)
    _S['motto'] = ParagraphStyle('mt', parent=base['Normal'], alignment=TA_CENTER,
                                 fontSize=8.5, leading=10, textColor=colors.HexColor('#333333'),
                                 fontName='Helvetica-Oblique')
    _S['sub'] = ParagraphStyle('s', parent=base['Normal'], alignment=TA_CENTER,
                               fontSize=10, spaceAfter=8, spaceBefore=2, fontName='Helvetica-Bold')
    _S['h'] = ParagraphStyle('h', parent=base['Heading4'], textColor=_PRIMARY,
                             spaceBefore=8, spaceAfter=4)
    _S['cell'] = ParagraphStyle('c', parent=base['Normal'], fontSize=8.5)
    _S['small'] = ParagraphStyle('sm', parent=base['Normal'], fontSize=7.5,
                                 textColor=colors.grey)
    return _S


def _school_dict(school):
    """Accept either a school-profile dict or a bare name string (back-compat)."""
    if isinstance(school, dict):
        return school
    return {'name': school or 'School', 'address': '', 'phone': '', 'email': '',
            'motto': '', 'logo_path': None}


def _card_flowables(student, report_data, term, school,
                    affective_traits, rating_labels):
    """The flowables for one student's report sheet — shared by the single-card
    and whole-class batch renderers so both stay pixel-identical."""
    e = []
    from utils.school import logo_flowable, logo_header_flowable
    sch = _school_dict(school)
    logo = logo_flowable(max_h_mm=18, max_w_mm=30, path=sch.get('logo_path'))
    name = sch.get('name') or 'School'
    sub_text = f'{term.full_name} — Report Sheet'

    # Letterhead: logo (only colour) beside centred name + full contact details.
    items = [(Paragraph(_esc(name), _S['title']), name, 'Helvetica-Bold', 16)]
    if sch.get('address'):
        items.append((Paragraph(_esc(sch['address']), _S['school_line']), sch['address'], 'Helvetica', 9))
    contact = ' · '.join(x for x in [
        (f"Tel: {sch['phone']}" if sch.get('phone') else ''), sch.get('email') or ''] if x)
    if contact:
        items.append((Paragraph(_esc(contact), _S['school_line']), contact, 'Helvetica', 9))
    if sch.get('motto'):
        items.append((Paragraph(_esc(sch['motto']), _S['motto']), sch['motto'], 'Helvetica-Oblique', 8.5))
    items.append((Paragraph(_esc(sub_text), _S['sub']), sub_text, 'Helvetica-Bold', 10))

    header = logo_header_flowable(logo, items) if logo is not None else None
    if header is not None:
        e.append(header)
    else:
        e.extend(it[0] for it in items)

    ts = report_data.get('term_summary')
    pos = ts.position_in_class if (ts and ts.position_in_class) else '—'
    att = (f'{ts.attendance_percentage}%' if (ts and ts.attendance_percentage is not None) else '—')
    e.append(_info_table([
        [('Name', student.full_name), ('Exam No', student.student_id)],
        [('Class', report_data['assignment'].display_name), ('No. in Class', report_data.get('no_in_class', '—'))],
        [('Term', term.name), ('Session', term.session.name if term.session else '')],
        [('Class Position', pos), ('Attendance', att)],
    ], [95 * mm, 75 * mm]))
    e.append(Spacer(1, 6))

    # Scores table
    ats = report_data['assessment_types']
    header = ['Subject'] + [(a.short_name or a.name) for a in ats] + ['Total', 'Grade', 'Remark']
    data = [header]
    for row in report_data['subjects']:
        cells = [row['subject'].name]
        cells += [('' if row['assessments'].get(a.id) is None else row['assessments'].get(a.id)) for a in ats]
        cells += [row['total'], row['grade'], row['remark']]
        data.append([str(c) for c in cells])
    n = len(ats)
    subj_w = 46 * mm
    rest = 170 * mm - subj_w
    at_w = (rest * 0.5) / max(n, 1)
    tail = (rest * 0.5) / 3
    score_tbl = Table(data, colWidths=[subj_w] + [at_w] * n + [tail, tail, tail], repeatRows=1)
    score_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), _PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, _LIGHT]),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    e.append(score_tbl)
    e.append(Spacer(1, 6))

    # Summary line
    e.append(_info_table([
        [('No. of Subjects', report_data['total_subjects']), ('Scores Obtainable', report_data.get('scores_obtainable', '—'))],
        [('Score Obtained', round(report_data['total_score'], 1)), ('Average Mark', f"{report_data.get('average_pct', report_data['average'])}%")],
        [('Result Status', report_data.get('result_status', '')), ('Overall Grade', report_data['overall_grade'])],
    ] + ([[('Next Term Fees', report_data['next_term_fees']), ('Next Term Begins', report_data.get('next_term_begins', ''))]]
         if report_data.get('next_term_fees') or report_data.get('next_term_begins') else []),
        [95 * mm, 75 * mm]))

    # Grade key
    if report_data.get('grade_scale'):
        key = ' · '.join(f"{_esc(b.grade)} ({b.min_score}-{b.max_score})" for b in report_data['grade_scale'])
        e.append(Paragraph('Grade Key', _S['h']))
        e.append(Paragraph(key, _S['small']))

    # Affective
    aff = ts.affective_map if ts else {}
    if aff:
        e.append(Paragraph('Affective Domain', _S['h']))
        adata = [['Trait', 'Rating']]
        for k, label in affective_traits:
            if aff.get(k):
                adata.append([label, f"{aff[k]}/5 · {rating_labels.get(aff[k], '')}"])
        at_tbl = Table(adata, colWidths=[90 * mm, 80 * mm])
        at_tbl.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#dddddd')),
            ('BACKGROUND', (0, 0), (-1, 0), _LIGHT),
        ]))
        e.append(at_tbl)

    # Comments
    if ts and (ts.teacher_comment or ts.principal_comment):
        e.append(Paragraph('Comments', _S['h']))
        if ts.teacher_comment:
            e.append(Paragraph(f"<b>Form teacher:</b> {_esc(ts.teacher_comment)}", _S['cell']))
        if ts.principal_comment:
            e.append(Paragraph(f"<b>Principal:</b> {_esc(ts.principal_comment)}", _S['cell']))

    return e


def report_card_pdf(student, report_data, term, school,
                    affective_traits, rating_labels):
    """A single student's report sheet as a one-PDF buffer. ``school`` may be the
    full school-profile dict (name/address/phone/email/motto/logo) or a name str."""
    _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=14 * mm, bottomMargin=14 * mm,
                            leftMargin=12 * mm, rightMargin=12 * mm,
                            title=f'Report — {student.full_name}')
    doc.build(_card_flowables(student, report_data, term, school,
                              affective_traits, rating_labels))
    buf.seek(0)
    return buf


def batch_report_cards_pdf(cards, school, affective_traits, rating_labels, *, title='Report Cards'):
    """A whole class's report sheets in one PDF, one student per page.

    ``cards`` is an iterable of (student, report_data, term). Reuses the exact
    single-card layout so batch output matches the individual downloads."""
    _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=14 * mm, bottomMargin=14 * mm,
                            leftMargin=12 * mm, rightMargin=12 * mm, title=title)
    flow = []
    first = True
    for (student, report_data, term) in cards:
        if not report_data:
            continue
        if not first:
            flow.append(PageBreak())
        first = False
        flow.extend(_card_flowables(student, report_data, term, school,
                                    affective_traits, rating_labels))
    if not flow:
        flow.append(Paragraph('No results to export.', _S['sub']))
    doc.build(flow)
    buf.seek(0)
    return buf
