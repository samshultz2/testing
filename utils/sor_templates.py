"""Statement of Result design templates (Phase 2 — document design).

A Statement of Result summarises a graduate's overall internal performance:
per-subject results (aggregated across their senior-secondary career) with grades
and a cumulative average. Like the other document designs, every layout is driven
by the same data (``build_record``) — only the look changes.

Standard module interface (shared with transcript/SLC designs): ``TEMPLATES``,
``DEFAULT_TEMPLATE``, ``list_templates``, ``resolve``, ``build_flowables``,
``page_decorator``, ``is_landscape``, ``sample_ctx``.
"""
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, HRFlowable

from utils import transcript_templates as _tt

P_W = 165 * mm


def _esc(v):
    from utils.web_exports import pdf_escape
    return pdf_escape(str(v if v is not None else ''))


def _styles():
    ss = getSampleStyleSheet()
    return {
        'body': ParagraphStyle('b', parent=ss['Normal'], fontSize=10.5, leading=16,
                               alignment=TA_JUSTIFY, spaceAfter=6),
        'left': ParagraphStyle('l', parent=ss['Normal'], fontSize=10, leading=15),
        'center': ParagraphStyle('c', parent=ss['Normal'], alignment=TA_CENTER, fontSize=10),
        'small': ParagraphStyle('s', parent=ss['Normal'], fontSize=8, textColor=colors.HexColor('#64748b')),
        'cell': ParagraphStyle('cell', parent=ss['Normal'], fontSize=8.5, leading=11),
    }


def _overall(academic):
    """[(subject, overall_score, grade)] averaged across the student's career,
    plus the cumulative average."""
    m = _tt._matrix(academic)
    rows = []
    for subj in m['subjects']:
        cells = m['grid'].get(subj, {})
        scores = [c.get('score') for c in cells.values() if c.get('score') is not None]
        if scores:
            avg = round(sum(scores) / len(scores), 1)
            rows.append((subj, avg, _tt._grade(avg)))
    return rows, m['cumulative']


def _remark(cum):
    if cum is None:
        return ''
    return ('Distinction' if cum >= 75 else 'Upper Credit' if cum >= 65 else 'Credit'
            if cum >= 55 else 'Pass' if cum >= 45 else 'Fair')


def _letterhead(ctx, accent, S, centered=True):
    name, addr, contact = _tt._header_lines(ctx['school'])
    nm = ParagraphStyle('nm', parent=S['center'] if centered else S['left'],
                        fontSize=16, leading=19, textColor=accent, fontName='Helvetica-Bold')
    sub = ParagraphStyle('sub', parent=S['center'] if centered else S['left'],
                         fontSize=8.5, textColor=colors.HexColor('#475569'))
    lines = [Paragraph(_esc(name), nm)]
    if addr:
        lines.append(Paragraph(_esc(addr), sub))
    if contact:
        lines.append(Paragraph(_esc('Tel: ' + contact), sub))
    logo = _tt._logo()
    if logo is not None:
        t = Table([[logo, lines]], colWidths=[30 * mm, P_W - 30 * mm])
        t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
        return [t]
    return lines


def _fields(pairs, S):
    rows = [[Paragraph(f'<b>{_esc(k)}</b>', S['left']), Paragraph(_esc(v), S['left'])]
            for k, v in pairs if v]
    if not rows:
        return []
    t = Table(rows, colWidths=[42 * mm, P_W - 42 * mm])
    t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                           ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
    return [t]


def _result_table(rows, S, accent):
    data = [['S/N', 'Subject', 'Score', 'Grade', 'Remark']]
    remark_by_grade = {'A': 'Excellent', 'B': 'Very good', 'C': 'Credit', 'D': 'Pass', 'F': 'Fail'}
    for i, (subj, score, grade) in enumerate(rows, 1):
        data.append([str(i), Paragraph(_esc(subj), S['cell']), _tt._fmt(score), grade,
                     remark_by_grade.get(grade, '')])
    t = Table(data, colWidths=[12 * mm, 73 * mm, 22 * mm, 22 * mm, 36 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 8.5), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), accent), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#94a3b8')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'), ('ALIGN', (2, 0), (3, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')])]))
    return t


def _grade_key(S):
    data = [['A', '70–100', 'Excellent'], ['B', '60–69', 'Very good'], ['C', '50–59', 'Credit'],
            ['D', '40–49', 'Pass'], ['F', '0–39', 'Fail']]
    t = Table([['Grade', 'Mark', 'Remark']] + data, colWidths=[18 * mm, 24 * mm, 34 * mm])
    t.setStyle(TableStyle([('FONTSIZE', (0, 0), (-1, -1), 7.5), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                           ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
                           ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
    return [Paragraph('<b>Key to grading</b>', S['small']), Spacer(1, 3), t]


def _sig(S, labels=('Principal', 'Registrar')):
    cells = [['_' * 24 for _ in labels], [Paragraph(f'<b>{_esc(x)}</b>', S['small']) for x in labels]]
    t = Table(cells, colWidths=[P_W / len(labels)] * len(labels))
    t.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('TOPPADDING', (0, 1), (-1, 1), 2)]))
    return [Spacer(1, 22), t]


def _summary_line(cum, S):
    if cum is None:
        return []
    return [Spacer(1, 6),
            Paragraph(f"<b>Cumulative Average:</b> {cum}% &nbsp;·&nbsp; "
                      f"<b>Overall Remark:</b> {_esc(_remark(cum))}", S['left'])]


# ---------------------------------------------------------------------------
# templates
# ---------------------------------------------------------------------------
def _t_classic(ctx):
    S = _styles()
    accent = colors.HexColor('#0e8a64')
    rows, cum = _overall(ctx['academic'])
    el = _letterhead(ctx, colors.HexColor('#0e3a2f'), S)
    el += [Spacer(1, 4), HRFlowable(width='100%', thickness=1.1, color=accent)]
    el.append(Paragraph('STATEMENT OF RESULT', ParagraphStyle(
        'ti', parent=S['center'], fontSize=14, fontName='Helvetica-Bold', textColor=accent,
        spaceBefore=8, spaceAfter=8)))
    el += _fields([('Name', ctx['student'].full_name), ('Admission No.', ctx['student'].student_id),
                   ('Sex', ctx['student'].gender), ('Graduation', ctx.get('grad_when'))], S)
    el.append(Spacer(1, 6))
    el.append(_result_table(rows, S, accent) if rows
              else Paragraph('No internal results are on record for this student.', S['body']))
    el += _summary_line(cum, S)
    el += [Spacer(1, 8)] + _grade_key(S) + _sig(S)
    return el


def _t_official(ctx):
    S = _styles()
    accent = colors.HexColor('#1f2937')
    rows, cum = _overall(ctx['academic'])
    hdr = ParagraphStyle('h', parent=S['center'], fontSize=13, fontName='Helvetica-Bold')
    el = _letterhead(ctx, accent, S)
    el += [Spacer(1, 4),
           Table([[Paragraph('STATEMENT OF RESULT', hdr)]], colWidths=[P_W],
                 style=TableStyle([('BOX', (0, 0), (-1, -1), 1, accent),
                                   ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f1f5f9')),
                                   ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)])),
           Spacer(1, 8)]
    info = [Paragraph(f"<b>Name:</b> {_esc(ctx['student'].full_name)}", S['left']),
            Paragraph(f"<b>Admission No.:</b> {_esc(ctx['student'].student_id)}", S['left']),
            Paragraph(f"<b>Sex:</b> {_esc(ctx['student'].gender)} &nbsp; "
                      f"<b>Graduation:</b> {_esc(ctx.get('grad_when'))}", S['left'])]
    box = Table([[info]], colWidths=[P_W])
    box.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.6, accent), ('LEFTPADDING', (0, 0), (-1, -1), 8),
                             ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    el += [box, Spacer(1, 8)]
    el.append(_result_table(rows, S, accent) if rows
              else Paragraph('No internal results are on record.', S['body']))
    el += _summary_line(cum, S)
    el.append(Paragraph("This statement is issued as a summary of the candidate's internal academic "
                        "record and does not replace the certificate.", S['small']))
    el += _sig(S)
    return el


def _t_sessional(ctx):
    """Per-session breakdown: each session's subjects, score & grade."""
    S = _styles()
    accent = colors.HexColor('#4338ca')
    m = _tt._matrix(ctx['academic'])
    el = _letterhead(ctx, accent, S)
    el += [Spacer(1, 4), HRFlowable(width='100%', thickness=1.1, color=accent)]
    el.append(Paragraph('STATEMENT OF RESULT', ParagraphStyle(
        'ti', parent=S['center'], fontSize=14, fontName='Helvetica-Bold', textColor=accent,
        spaceBefore=8, spaceAfter=6)))
    el += _fields([('Name', ctx['student'].full_name), ('Admission No.', ctx['student'].student_id)], S)
    if not m['subjects']:
        return el + [Paragraph('No internal results are on record.', S['body'])] + _sig(S)
    for sess in m['sessions']:
        cap = ParagraphStyle('cap', parent=S['small'], fontName='Helvetica-Bold', textColor=accent)
        el += [Spacer(1, 6), Paragraph(f"{m['ss_labels'].get(sess, sess)} — {_esc(sess)}", cap)]
        rows = []
        for subj in m['subjects']:
            sc = m['sess_scores'].get((subj, sess))
            if sc is not None:
                rows.append((subj, sc, _tt._grade(sc)))
        el.append(_result_table(rows, S, accent) if rows
                  else Paragraph('No results recorded for this session.', S['small']))
    el += _summary_line(m['cumulative'], S) + _sig(S)
    return el


def _t_modern(ctx):
    S = _styles()
    accent = colors.HexColor('#0369a1')
    rows, cum = _overall(ctx['academic'])
    name, addr, contact = _tt._header_lines(ctx['school'])
    bar_name = ParagraphStyle('bn', parent=S['left'], fontSize=15, fontName='Helvetica-Bold', textColor=colors.white)
    bar_sub = ParagraphStyle('bs', parent=S['left'], fontSize=8, textColor=colors.HexColor('#e0f2fe'))
    inner = [Paragraph(_esc(name), bar_name)]
    if addr:
        inner.append(Paragraph(_esc(addr), bar_sub))
    bar = Table([[inner, Paragraph('STATEMENT<br/>OF RESULT', ParagraphStyle(
        'bt', parent=S['left'], fontSize=12, fontName='Helvetica-Bold', textColor=colors.white, alignment=2))]],
        colWidths=[P_W - 45 * mm, 45 * mm])
    bar.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), accent), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                             ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                             ('LEFTPADDING', (0, 0), (0, 0), 10), ('RIGHTPADDING', (-1, -1), (-1, -1), 10)]))
    el = [bar, Spacer(1, 8)]
    el += _fields([('Name', ctx['student'].full_name), ('Admission No.', ctx['student'].student_id),
                   ('Graduation', ctx.get('grad_when'))], S)
    el.append(Spacer(1, 6))
    el.append(_result_table(rows, S, accent) if rows
              else Paragraph('No internal results are on record.', S['body']))
    el += _summary_line(cum, S)
    el += [Spacer(1, 8)] + _grade_key(S) + _sig(S)
    return el


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
SOR_TEMPLATES = {
    'classic': {'name': 'Classic (default)', 'render': _t_classic,
                'description': 'Clean statement with an aggregated subject/score/grade table and grading key.'},
    'official': {'name': 'Official (boxed)', 'render': _t_official,
                 'description': 'Boxed official statement with a student-info panel and results table.'},
    'sessional': {'name': 'Per-session', 'render': _t_sessional,
                  'description': 'Results broken down by senior-secondary session (SS1–SS3).'},
    'modern': {'name': 'Modern Banner', 'render': _t_modern,
               'description': 'Coloured header bar with an aggregated results table and grading key.'},
}
TEMPLATES = SOR_TEMPLATES
DEFAULT_TEMPLATE = 'classic'


def list_templates():
    return [{'key': k, 'name': v['name'], 'description': v['description']}
            for k, v in SOR_TEMPLATES.items()]


def resolve(key):
    return SOR_TEMPLATES.get(key) or SOR_TEMPLATES[DEFAULT_TEMPLATE]


def build_flowables(key, ctx):
    return resolve(key)['render'](ctx)


def page_decorator(key):
    return resolve(key).get('decorator')


def is_landscape(key):
    return bool(resolve(key).get('landscape'))


def sample_ctx(school):
    return _tt.sample_ctx(school)
