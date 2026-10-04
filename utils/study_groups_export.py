"""PDF and Excel exports for a Study Groups set (the HD-image export is
client-side -- see static/js/study-groups.js -- since it's just a screenshot
of the already-rendered board, same as this app's analytics dashboards)."""
import io

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from utils.numfmt import fmt_num as _n


def build_pdf(data, school):
    """A printable sheet: one table per group, leader marked, for the given
    ``_set_payload()`` data dict."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=12 * mm, bottomMargin=12 * mm,
                            leftMargin=14 * mm, rightMargin=14 * mm)
    base = getSampleStyleSheet()
    title_style = ParagraphStyle('t', parent=base['Title'], fontSize=16, alignment=TA_CENTER)
    sub_style = ParagraphStyle('s', parent=base['Normal'], fontSize=10, alignment=TA_CENTER,
                               textColor=colors.HexColor('#444444'))
    group_hdr = ParagraphStyle('g', parent=base['Normal'], fontSize=12, fontName='Helvetica-Bold',
                               spaceBefore=10, spaceAfter=4)

    flow = []
    school_name = (school or {}).get('name') or 'School'
    flow.append(Paragraph(school_name, title_style))
    flow.append(Paragraph(data.get('title') or 'Study Groups', sub_style))
    flow.append(Paragraph(
        f"{data.get('class_name', '')} &middot; {data.get('term_name', '')} "
        f"&middot; {data.get('num_groups')} group(s) of {data.get('group_size')}", sub_style))
    flow.append(Spacer(1, 6 * mm))

    for g in data.get('groups', []):
        flow.append(Paragraph(g['label'], group_hdr))
        rows = [['#', 'Student', 'Admission No.', 'Role']]
        for i, m in enumerate(g['members'], start=1):
            role = 'Leader' if m['is_leader'] else ''
            rows.append([str(i), m['name'], m['admission_no'], role])
        t = Table(rows, colWidths=[10 * mm, 80 * mm, 40 * mm, 25 * mm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#999999')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f3f4f6')]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        flow.append(t)
        flow.append(Spacer(1, 4 * mm))

    doc.build(flow)
    buf.seek(0)
    return buf


def build_xlsx(data):
    """One row per student: group, leader flag, basis average."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment

    wb = Workbook()
    ws = wb.active
    ws.title = 'Study Groups'
    head_font = Font(bold=True, color='FFFFFF')
    ws.append([data.get('title') or 'Study Groups'])
    ws.append([f"{data.get('class_name', '')} - {data.get('term_name', '')}"])
    ws.append([])
    header = ['Group', 'Student', 'Admission No.', 'Leader', 'Previous Term Average']
    ws.append(header)
    for cell in ws[ws.max_row]:
        cell.font = head_font
        cell.alignment = Alignment(horizontal='center')
    for g in data.get('groups', []):
        for m in g['members']:
            ws.append([g['label'], m['name'], m['admission_no'],
                      'Yes' if m['is_leader'] else '',
                      _n(m['basis_average']) if m['basis_average'] is not None else ''])
    for col in ws.columns:
        width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 8), 40)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
