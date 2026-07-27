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


# Portrait body height available before the shared verification footer. The real
# value is supplied per-render via ctx['_avail'] (page − margins − footer); this is
# a safe fallback when a template is built outside the document pipeline.
_P_BODY_H = 273 * mm - 46 * mm

def page_margins(key):
    """Statements fill the page with only a little margin (see reference layouts).
    Ornate-border designs keep enough room to clear their printed frame."""
    if key in ('waec', 'bordered'):
        return (14, 14, 15, 15)
    return (12, 12, 14, 14)


def _logo_center(max_h=16, max_w=42):
    """The school logo, centred, for designs that don't use ``_letterhead``.
    Every document must show the logo when the school has uploaded one."""
    try:
        from utils.school import logo_flowable
        img = logo_flowable(max_h_mm=max_h, max_w_mm=max_w)
    except Exception:
        img = None
    if img is None:
        return []
    img.hAlign = 'CENTER'
    return [img, Spacer(1, 4)]


def _fill_pad(above, below, n_rows, avail, width=P_W, header_h=11 * mm,
              line_pt=15, lo_pt=4, hi_pt=10):
    """Vertical cell padding (points) that stretches the real result rows so the
    table fills the page — instead of padding it out with empty rows. Clamped so a
    short result stays reasonable and never overshoots the page; any slack left over
    is taken up by the elastic gap above the signatures."""
    # Rows keep a comfortable, uniform height — the page is filled with real
    # content blocks (bio, summary, grade key, Principal's Remarks), not by
    # stretching table rows (which read as sparse and wrong).
    return 5


def _measure(flowables, width, avail):
    """Approximate the natural stacked height of a list of flowables."""
    total = 0
    for f in flowables:
        try:
            total += f.getSpaceBefore()
        except Exception:
            pass
        try:
            _w, hh = f.wrap(width, avail)
            total += hh
        except Exception:
            pass
        try:
            total += f.getSpaceAfter()
        except Exception:
            pass
    return total


def _page_fill(body, sig, avail=_P_BODY_H, width=P_W):
    """Return body + an elastic gap + signatures so the signature block sits near
    the page bottom (filling the page) instead of hugging the content. Falls back
    to a plain concatenation when the content already fills the page."""
    gap = avail - _measure(body, width, avail) - _measure(sig, width, avail)
    filler = [Spacer(1, gap)] if gap > 8 * mm else []
    return list(body) + filler + list(sig)


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


def _pron(gender):
    g = (gender or '').strip().lower()
    if g.startswith('m'):
        return {'S': 'He', 's': 'he', 'p': 'his'}
    if g.startswith('f'):
        return {'S': 'She', 's': 'she', 'p': 'her'}
    return {'S': 'They', 's': 'they', 'p': 'their'}


def _remarks(ctx, S):
    """A data-driven Principal's Remarks block (fills the page with real content,
    the way the reference statements do — not by stretching table rows)."""
    st = ctx['student']
    cum = (ctx.get('academic') or {}).get('cumulative')
    pr = _pron(getattr(st, 'gender', None))
    perf = (_remark(cum) or 'satisfactory').lower()
    name = _esc(getattr(st, 'first_name', None) or (st.full_name or '').split(' ')[0] or 'The candidate')
    text = (f"{name} demonstrated {perf} academic performance and maintained good conduct "
            f"and discipline throughout {pr['p']} time in this school. {pr['S']} is of good "
            f"moral character and is hereby recommended for further academic pursuits and "
            f"future endeavours.")
    return [Spacer(1, 8),
            Paragraph(f"<b>Principal's Remarks:</b> <i>{text}</i>", S['body'])]


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


def _result_table(rows, S, accent, pad=4):
    cell = ParagraphStyle('rc', parent=S['cell'], fontSize=10.5, leading=13)
    data = [['S/N', 'Subject', 'Score', 'Grade', 'Remark']]
    remark_by_grade = {'A': 'Excellent', 'B': 'Very good', 'C': 'Credit', 'D': 'Pass', 'F': 'Fail'}
    for i, (subj, score, grade) in enumerate(rows, 1):
        data.append([str(i), Paragraph(_esc(subj), cell), _tt._fmt(score), grade,
                     remark_by_grade.get(grade, '')])
    t = Table(data, colWidths=[12 * mm, 73 * mm, 22 * mm, 22 * mm, 36 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10.5), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), accent), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#94a3b8')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'), ('ALIGN', (2, 0), (3, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 1), (-1, -1), pad), ('BOTTOMPADDING', (0, 1), (-1, -1), pad),
        ('TOPPADDING', (0, 0), (-1, 0), 4), ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')])]))
    return t


def _grade_key(S, ssce=False):
    if ssce:
        data = [['A1', 'Distinction'], ['B2', 'Very Good'], ['B3', 'Good'], ['C4–C6', 'Credit'],
                ['D7–E8', 'Pass'], ['F9', 'Fail']]
        t = Table([['Grade', 'Remark']] + data, colWidths=[26 * mm, 50 * mm])
    else:
        data = [['A', '70–100', 'Excellent'], ['B', '60–69', 'Very good'], ['C', '50–59', 'Credit'],
                ['D', '40–49', 'Pass'], ['F', '0–39', 'Fail']]
        t = Table([['Grade', 'Mark', 'Remark']] + data, colWidths=[18 * mm, 24 * mm, 34 * mm])
    t.setStyle(TableStyle([('FONTSIZE', (0, 0), (-1, -1), 7.5), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                           ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
                           ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
    return [Paragraph('<b>Key to grading</b>', S['small']), Spacer(1, 3), t]


def _statement_rows(ctx):
    """Single results source for a statement: the WAEC/NECO result when available
    (grade + remark), otherwise the internal overall result (score + grade).
    Returns (rows, is_ssce, year) where each row is (subject, score, grade, remark)
    and ``score`` is None for a WAEC-sourced row."""
    waec = ctx.get('waec') or {}
    subs = waec.get('subjects') or []
    if subs:
        rows = [(s.get('subject'), None, s.get('grade') or '',
                 _WAEC_REMARK.get((s.get('grade') or '').upper(), '')) for s in subs]
        return rows, True, waec.get('year')
    overall, _cum = _overall(ctx['academic'])
    rmk = {'A': 'Excellent', 'B': 'Very good', 'C': 'Credit', 'D': 'Pass', 'F': 'Fail'}
    rows = [(subj, sc, g, rmk.get(g, '')) for subj, sc, g in overall]
    return rows, False, None


def _main_table(rows, is_ssce, S, accent, pad=4):
    if is_ssce:
        return _ssce_table([(r[0], r[2], r[3]) for r in rows], S, accent, pad=pad)
    return _result_table([(r[0], r[1], r[2]) for r in rows], S, accent, pad=pad)


def _stmt_summary(ctx, rows, is_ssce, S):
    """The little result details, stacked vertically."""
    if is_ssce:
        credited = sum(1 for r in rows if (r[2] or '').upper() in ('A1', 'B2', 'B3', 'C4', 'C5', 'C6'))
        passed = sum(1 for r in rows if r[2] and (r[2] or '').upper() != 'F9')
        failed = sum(1 for r in rows if (r[2] or '').upper() == 'F9')
        return [_summary_strip({'registered': len(rows), 'credited': credited,
                                'passed': passed, 'failed': failed}, S, ssce=True)]
    cum = (ctx.get('academic') or {}).get('cumulative')
    if cum is None:
        return []
    return [Paragraph(f"<b>Cumulative Average:</b> {cum}%", S['left']),
            Paragraph(f"<b>Overall Remark:</b> {_esc(_remark(cum))}", S['left'])]


def _sig(S, labels=('Principal', 'Registrar')):
    cells = [['_' * 24 for _ in labels], [Paragraph(f'<b>{_esc(x)}</b>', S['small']) for x in labels]]
    t = Table(cells, colWidths=[P_W / len(labels)] * len(labels))
    t.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('TOPPADDING', (0, 1), (-1, 1), 2)]))
    return [Spacer(1, 22), t]


def _waec_block(ctx, S, accent):
    """WAEC result table (subject + grade), when the student has one on record."""
    waec = ctx.get('waec') or {}
    subs = waec.get('subjects') or []
    if not subs:
        return []
    yr = waec.get('year')
    title = 'WAEC Result' + (f' — {yr}' if yr else '')
    rows = [['S/N', 'Subject', 'Grade']]
    for i, s in enumerate(subs, 1):
        rows.append([str(i), Paragraph(_esc(s.get('subject')), S['cell']), s.get('grade') or '—'])
    t = Table(rows, colWidths=[12 * mm, 113 * mm, 40 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 8.5), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), accent), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#94a3b8')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'), ('ALIGN', (2, 0), (2, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')])]))
    return [Spacer(1, 10), Paragraph(f'<b>{_esc(title)}</b>', S['left']), Spacer(1, 3), t]


def _summary_line(cum, S):
    if cum is None:
        return []
    return [Spacer(1, 6),
            Paragraph(f"<b>Cumulative Average:</b> {cum}% &nbsp;·&nbsp; "
                      f"<b>Overall Remark:</b> {_esc(_remark(cum))}", S['left'])]


_WAEC_REMARK = {'A1': 'Distinction', 'B2': 'Very Good', 'B3': 'Good', 'C4': 'Credit',
                'C5': 'Credit', 'C6': 'Credit', 'D7': 'Pass', 'E8': 'Pass', 'F9': 'Fail'}


def _ssce_rows(ctx):
    """(rows, summary, source) for an SSCE-style statement. Prefers the WAEC
    result; falls back to internal overall results if no WAEC is on record."""
    waec = ctx.get('waec') or {}
    subs = waec.get('subjects') or []
    if subs:
        rows = [(s.get('subject'), s.get('grade') or '', _WAEC_REMARK.get((s.get('grade') or '').upper(), ''))
                for s in subs]
        credited = sum(1 for _, g, _r in rows if g.upper() in ('A1', 'B2', 'B3', 'C4', 'C5', 'C6'))
        passed = sum(1 for _, g, _r in rows if g.upper() != 'F9' and g)
        failed = sum(1 for _, g, _r in rows if g.upper() == 'F9')
        _yr = waec.get('year')
        src = 'WAEC/NECO' + (f' — {_yr}' if _yr else '')
    else:
        overall, _cum = _overall(ctx['academic'])
        rmk = {'A': 'Excellent', 'B': 'Very good', 'C': 'Credit', 'D': 'Pass', 'F': 'Fail'}
        rows = [(subj, g, rmk.get(g, '')) for subj, sc, g in overall]
        credited = sum(1 for _, g, _r in rows if g in ('A', 'B', 'C'))
        passed = sum(1 for _, g, _r in rows if g and g != 'F')
        failed = sum(1 for _, g, _r in rows if g == 'F')
        src = 'internal records'
    summary = {'registered': len(rows), 'credited': credited, 'passed': passed, 'failed': failed}
    return rows, summary, src


def _ssce_table(rows, S, accent, pad=4, colWidths=(12 * mm, 95 * mm, 25 * mm, 35 * mm)):
    cell = ParagraphStyle('sc', parent=S['cell'], fontSize=10.5, leading=13)
    data = [['S/N', 'Subject', 'Grade', 'Remark']]
    for i, (subj, grade, remark) in enumerate(rows, 1):
        data.append([str(i), Paragraph(_esc(subj), cell), grade, remark])
    t = Table(data, colWidths=list(colWidths), repeatRows=1)
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10.5), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), accent), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#94a3b8')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'), ('ALIGN', (2, 0), (2, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 1), (-1, -1), pad), ('BOTTOMPADDING', (0, 1), (-1, -1), pad),
        ('TOPPADDING', (0, 0), (-1, 0), 4), ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')])]))
    return t


def _summary_strip(summary, S, ssce=True):
    """The result tally, stacked vertically (subjects offered, sittings, credits,
    passed, failed) rather than in one wide horizontal strip."""
    credit_label = 'Credits (C6 &amp; above)' if ssce else 'Credits'
    rows = [('Subjects offered', summary['registered']),
            ('Sittings', 1),
            (credit_label, summary['credited']),
            ('Subjects passed', summary['passed']),
            ('Subjects failed', summary['failed'])]
    data = [[Paragraph(f'<b>{lab}</b>', S['left']), Paragraph(str(val), S['left'])] for lab, val in rows]
    t = Table(data, colWidths=[52 * mm, 20 * mm], hAlign='LEFT')
    t.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor('#cbd5e1')),
                           ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#e2e8f0')),
                           ('ALIGN', (1, 0), (1, -1), 'CENTER'),
                           ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                           ('LEFTPADDING', (0, 0), (-1, -1), 6)]))
    return t


def _border_blue(canvas, doc):
    _ornate_border(canvas, doc, colors.HexColor('#1d4ed8'))


def _border_green(canvas, doc):
    _ornate_border(canvas, doc, colors.HexColor('#15803d'), dotted=True)


def _ornate_border(canvas, doc, color, dotted=False):
    w, h = doc.pagesize
    canvas.saveState()
    canvas.setStrokeColor(color)
    canvas.setLineWidth(5)
    canvas.rect(9 * mm, 9 * mm, w - 18 * mm, h - 18 * mm, stroke=1, fill=0)
    canvas.setLineWidth(1)
    canvas.rect(12.5 * mm, 12.5 * mm, w - 25 * mm, h - 25 * mm, stroke=1, fill=0)
    canvas.setFillColor(color)
    r = 0.9 * mm
    step = 9 * mm
    x = 15 * mm
    while x < w - 15 * mm:
        canvas.circle(x, 10.5 * mm, r, fill=1, stroke=0)
        canvas.circle(x, h - 10.5 * mm, r, fill=1, stroke=0)
        x += step
    y = 15 * mm
    while y < h - 15 * mm:
        canvas.circle(10.5 * mm, y, r, fill=1, stroke=0)
        canvas.circle(w - 10.5 * mm, y, r, fill=1, stroke=0)
        y += step
    canvas.restoreState()


# ---------------------------------------------------------------------------
# templates
# ---------------------------------------------------------------------------
def _t_classic(ctx):
    S = _styles()
    accent = colors.HexColor('#0e8a64')
    rows, is_ssce, year = _statement_rows(ctx)
    avail = ctx.get('_avail', _P_BODY_H)
    above = _letterhead(ctx, colors.HexColor('#0e3a2f'), S)
    above += [Spacer(1, 4), HRFlowable(width='100%', thickness=1.1, color=accent),
              Paragraph('STATEMENT OF RESULT', ParagraphStyle(
                  'ti', parent=S['center'], fontSize=14, fontName='Helvetica-Bold', textColor=accent,
                  spaceBefore=8, spaceAfter=8))]
    above += _fields([('Name', ctx['student'].full_name), ('Admission No.', ctx['student'].student_id),
                      ('Sex', ctx['student'].gender), ('Graduation', ctx.get('grad_when'))], S)
    above.append(Spacer(1, 6))
    sig = _sig(S)
    mid = (_stmt_summary(ctx, rows, is_ssce, S) + [Spacer(1, 8)] + _grade_key(S, ssce=is_ssce)
           + _remarks(ctx, S))
    if not rows:
        return _page_fill(above + [Paragraph('No results are on record for this student.',
                                             S['body'])], sig, avail=avail)
    pad = _fill_pad(above, mid + sig, len(rows), avail)
    body = above + [_main_table(rows, is_ssce, S, accent, pad=pad)] + mid
    return _page_fill(body, sig, avail=avail)


def _t_official(ctx):
    S = _styles()
    accent = colors.HexColor('#1f2937')
    rows, is_ssce, year = _statement_rows(ctx)
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
    avail = ctx.get('_avail', _P_BODY_H)
    sig = _sig(S)
    mid = (_stmt_summary(ctx, rows, is_ssce, S) + _remarks(ctx, S) + [Spacer(1, 6),
           Paragraph("This statement is issued as a summary of the candidate's academic "
                     "record and does not replace the certificate.", S['small'])])
    if not rows:
        return _page_fill(el + [Paragraph('No results are on record.', S['body'])], sig, avail=avail)
    pad = _fill_pad(el, mid + sig, len(rows), avail)
    body = el + [_main_table(rows, is_ssce, S, accent, pad=pad)] + mid
    return _page_fill(body, sig, avail=avail)


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
    avail = ctx.get('_avail', _P_BODY_H)
    if not m['subjects']:
        return _page_fill(el + [Paragraph('No internal results are on record.', S['body'])],
                          _sig(S), avail=avail)
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
    el += _summary_line(m['cumulative'], S)
    el += _waec_block(ctx, S, accent)
    return _page_fill(el, _sig(S), avail=avail)


def _t_modern(ctx):
    S = _styles()
    accent = colors.HexColor('#0369a1')
    rows, is_ssce, year = _statement_rows(ctx)
    name, addr, contact = _tt._header_lines(ctx['school'])
    bar_name = ParagraphStyle('bn', parent=S['left'], fontSize=15, fontName='Helvetica-Bold', textColor=colors.white)
    bar_sub = ParagraphStyle('bs', parent=S['left'], fontSize=8, textColor=colors.HexColor('#e0f2fe'))
    inner = [Paragraph(_esc(name), bar_name)]
    if addr:
        inner.append(Paragraph(_esc(addr), bar_sub))
    title_cell = Paragraph('STATEMENT<br/>OF RESULT', ParagraphStyle(
        'bt', parent=S['left'], fontSize=12, fontName='Helvetica-Bold', textColor=colors.white, alignment=2))
    logo = None
    try:
        from utils.school import logo_flowable
        logo = logo_flowable(max_h_mm=14, max_w_mm=20)
    except Exception:
        logo = None
    if logo is not None:
        bar = Table([[logo, inner, title_cell]], colWidths=[24 * mm, P_W - 69 * mm, 45 * mm])
        bar_style = [('SPAN', (0, 0), (0, 0))]
    else:
        bar = Table([[inner, title_cell]], colWidths=[P_W - 45 * mm, 45 * mm])
        bar_style = []
    bar.setStyle(TableStyle(bar_style + [('BACKGROUND', (0, 0), (-1, -1), accent),
                             ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                             ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                             ('LEFTPADDING', (0, 0), (0, 0), 10), ('RIGHTPADDING', (-1, -1), (-1, -1), 10)]))
    el = [bar, Spacer(1, 8)]
    el += _fields([('Name', ctx['student'].full_name), ('Admission No.', ctx['student'].student_id),
                   ('Graduation', ctx.get('grad_when'))], S)
    el.append(Spacer(1, 6))
    avail = ctx.get('_avail', _P_BODY_H)
    sig = _sig(S)
    mid = (_stmt_summary(ctx, rows, is_ssce, S) + [Spacer(1, 8)] + _grade_key(S, ssce=is_ssce)
           + _remarks(ctx, S))
    if not rows:
        return _page_fill(el + [Paragraph('No results are on record.', S['body'])], sig, avail=avail)
    pad = _fill_pad(el, mid + sig, len(rows), avail)
    body = el + [_main_table(rows, is_ssce, S, accent, pad=pad)] + mid
    return _page_fill(body, sig, avail=avail)


def _t_institutional(ctx):
    """Federal-Polytechnic-style 'Statement of Examination Results' with a dark
    banner, student-info block, results table, summary strip and registrar line."""
    S = _styles()
    dark = colors.HexColor('#111827')
    el = _letterhead(ctx, dark, S)
    el += [Spacer(1, 4),
           Table([[Paragraph('STATEMENT OF EXAMINATION RESULTS', ParagraphStyle(
               'ti', parent=S['center'], fontSize=14, fontName='Helvetica-Bold', textColor=colors.white))]],
               colWidths=[P_W], style=TableStyle([('BACKGROUND', (0, 0), (-1, -1), dark),
                                                  ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)])),
           Spacer(1, 8)]
    el += _fields([('Student Name', ctx['student'].full_name),
                   ('Admission No.', ctx['student'].student_id),
                   ('Sex', ctx['student'].gender), ('Graduation', ctx.get('grad_when'))], S)
    el.append(Spacer(1, 6))
    avail = ctx.get('_avail', _P_BODY_H)
    rows, summary, src = _ssce_rows(ctx)
    ov_cum = (ctx.get('academic') or {}).get('cumulative')
    sig = _sig(S, labels=('Registrar', 'Principal'))
    mid = [Spacer(1, 6), _summary_strip(summary, S)]
    if ov_cum is not None:
        mid += _summary_line(ov_cum, S)
    mid += ([Spacer(1, 8)] + _grade_key(S, ssce=True) + _remarks(ctx, S) + [Spacer(1, 4),
            Paragraph(f"<i>Result computed from {_esc(src)}. Any alteration renders this "
                      f"result invalid.</i>", S['small'])])
    if not rows:
        return _page_fill(el + [Paragraph('No results are on record for this student.', S['body'])],
                          sig, avail=avail)
    pad = _fill_pad(el, mid + sig, len(rows), avail)
    body = el + [_ssce_table(rows, S, dark, pad=pad)] + mid
    return _page_fill(body, sig, avail=avail)


def _t_waec(ctx):
    """SSCE 'Statement of Result' inside an ornate blue border (WAEC/NECO look)."""
    S = _styles()
    blue = colors.HexColor('#1d4ed8')
    name, _a, _c = _tt._header_lines(ctx['school'])
    el = _logo_center() + [
        Paragraph(_esc(name), ParagraphStyle('nm', parent=S['center'], fontSize=16, leading=20,
                                             fontName='Helvetica-Bold', textColor=blue, spaceAfter=3)),
        Paragraph('Senior School Certificate Examination', S['center']),
        Paragraph('STATEMENT OF RESULT', ParagraphStyle(
            'ti', parent=S['center'], fontSize=13, fontName='Helvetica-Bold', textColor=blue,
            spaceBefore=4, spaceAfter=8))]
    el += _fields([('Candidate Name', ctx['student'].full_name),
                   ('Admission / Centre No.', ctx['student'].student_id),
                   ('Year', str((ctx.get('waec') or {}).get('year') or ctx.get('grad_when') or '')),
                   ('Sex', ctx['student'].gender)], S)
    el.append(Spacer(1, 6))
    avail = ctx.get('_avail', _P_BODY_H)
    rows, summary, src = _ssce_rows(ctx)
    sig = _sig(S, labels=("Principal's Signature", 'Date'))
    mid = [Spacer(1, 6), _summary_strip(summary, S)] + _remarks(ctx, S) + [Spacer(1, 6),
           Paragraph(f"Result computed from {_esc(src)}. Any alteration on this statement "
                     f"renders it invalid.", S['small'])]
    if not rows:
        return _page_fill(el + [Paragraph('No results are on record for this student.', S['body'])],
                          sig, avail=avail)
    pad = _fill_pad(el, mid + sig, len(rows), avail)
    body = el + [_ssce_table(rows, S, blue, pad=pad)] + mid
    return _page_fill(body, sig, avail=avail)


def _t_bordered(ctx):
    """Community-school-style statement inside a green dotted border."""
    S = _styles()
    green = colors.HexColor('#15803d')
    name, _a, _c = _tt._header_lines(ctx['school'])
    yr = (ctx.get('waec') or {}).get('year')
    el = _logo_center() + [
        Paragraph(_esc(name), ParagraphStyle('nm', parent=S['center'], fontSize=17, leading=21,
                                             fontName='Helvetica-Bold', textColor=green, spaceAfter=3)),
        Paragraph('WASC / SSCE' + (f' — {yr}' if yr else ''), S['center']),
        Paragraph('STATEMENT OF RESULT', ParagraphStyle(
            'ti', parent=S['center'], fontSize=13, fontName='Helvetica-Bold', textColor=colors.HexColor('#b91c1c'),
            spaceBefore=4, spaceAfter=8))]
    el += _fields([("Candidate's Name", ctx['student'].full_name),
                   ('Exam / Admission No.', ctx['student'].student_id)], S)
    el.append(Spacer(1, 6))
    avail = ctx.get('_avail', _P_BODY_H)
    rows, summary, src = _ssce_rows(ctx)
    sig = _sig(S, labels=('Principal', 'Date'))
    mid = [Spacer(1, 6), _summary_strip(summary, S, ssce=True)] + _remarks(ctx, S)
    if not rows:
        return _page_fill(el + [Paragraph('No results are on record for this student.', S['body'])],
                          sig, avail=avail)
    pad = _fill_pad(el, mid + sig, len(rows), avail)
    body = el + [_ssce_table(rows, S, green, pad=pad)] + mid
    return _page_fill(body, sig, avail=avail)


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
def _photo_box(w=26 * mm, h=32 * mm):
    t = Table([[Paragraph('PHOTOGRAPH', ParagraphStyle('ph', fontSize=6, alignment=1,
               textColor=colors.HexColor('#94a3b8')))]], colWidths=[w], rowHeights=[h])
    t.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#94a3b8')),
                           ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#eef2f7')),
                           ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
    return t


def _bio_pairs(pairs, S, width, label_w=38 * mm):
    rows = [[Paragraph(f'<b>{_esc(k)}:</b>', S['left']), Paragraph(_esc(v), S['left'])]
            for k, v in pairs if v]
    t = Table(rows, colWidths=[label_w, width - label_w])
    t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                           ('TOPPADDING', (0, 0), (-1, -1), 1.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5)]))
    return t


def _eagle_frame(canvas, doc):
    _ornate_border(canvas, doc, colors.HexColor('#15803d'))


def _t_eagle(ctx):
    """Faithful 'Eagle's Nest' replica: crested two-tone masthead, passport box,
    bio grid, subject/grade/remark table, distinctions summary, remarks and a red
    Statement-of-Results number."""
    S = _styles()
    green, navy = colors.HexColor('#15803d'), colors.HexColor('#1e3a8a')
    rows, is_ssce, year = _statement_rows(ctx)
    avail = ctx.get('_avail', _P_BODY_H)
    name, addr, contact = _tt._header_lines(ctx['school'])
    above = _logo_center(max_h=18, max_w=34) + [
        Paragraph(_esc(name), ParagraphStyle('nm', parent=S['center'], fontSize=18, leading=21,
                  fontName='Helvetica-Bold', textColor=navy))]
    if ctx['school'].get('motto'):
        above.append(Paragraph(f"<i>{_esc(ctx['school'].get('motto'))}</i>", ParagraphStyle(
            'mt', parent=S['center'], fontSize=8, textColor=green)))
    sub = ' · '.join([x for x in [addr, contact] if x])
    if sub:
        above.append(Paragraph(_esc(sub), S['small']))
    above.append(Paragraph('<font color="#15803d">STATEMENT OF </font><font color="#1e3a8a">RESULTS</font>',
                 ParagraphStyle('ti', parent=S['center'], fontSize=18, fontName='Helvetica-Bold',
                                spaceBefore=6, spaceAfter=6)))
    st = ctx['student']
    bio = _bio_pairs([('Full Name', st.full_name), ('Admission Number', st.student_id),
                      ('Gender', st.gender), ('Academic Session', ctx.get('grad_session') or ctx.get('admission_session')),
                      ('Graduation Year', ctx.get('grad_when')),
                      ('Candidate Number', getattr(st, 'jamb_reg_number', None) or st.student_id)],
                     S, P_W - 30 * mm)
    idrow = Table([[bio, _photo_box()]], colWidths=[P_W - 30 * mm, 30 * mm])
    idrow.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('ALIGN', (1, 0), (1, 0), 'RIGHT')]))
    above += [idrow, Spacer(1, 6)]
    sor_no = Paragraph(f"<b>Statement of Results Number:</b> "
                       f"<font color='#b91c1c'>{_esc((ctx.get('doc') or type('x',(),{'document_number':''})()).document_number or 'ENIS-SOR-0000000')}</font>",
                       S['left'])
    sig = _sig(S)
    mid = (_stmt_summary(ctx, rows, is_ssce, S) + [Spacer(1, 6)] + _grade_key(S, ssce=is_ssce)
           + _remarks(ctx, S) + [Spacer(1, 4), sor_no])
    if not rows:
        return _page_fill(above + [Paragraph('No results are on record.', S['body'])], sig, avail=avail)
    return _page_fill(above + [_main_table(rows, is_ssce, S, green, pad=5)] + mid, sig, avail=avail)


def _border_gold(canvas, doc):
    _ornate_border(canvas, doc, colors.HexColor('#b7791f'))


def _thin_frame(canvas, doc):
    w, h = doc.pagesize
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor('#1f2937'))
    canvas.setLineWidth(1.2)
    canvas.rect(10 * mm, 10 * mm, w - 20 * mm, h - 20 * mm, stroke=1, fill=0)
    canvas.restoreState()


def _t_banded(ctx):
    """Full-width colour masthead with the identity reversed out."""
    S = _styles()
    accent = colors.HexColor('#0c4a6e')
    rows, is_ssce, year = _statement_rows(ctx)
    avail = ctx.get('_avail', _P_BODY_H)
    name, addr, contact = _tt._header_lines(ctx['school'])
    logo = _tt._logo()
    inner = [Paragraph(_esc(name), ParagraphStyle('bn', parent=S['left'], fontSize=16,
                       fontName='Helvetica-Bold', textColor=colors.white, leading=19)),
             Paragraph('STATEMENT OF RESULT', ParagraphStyle('bt', parent=S['left'], fontSize=11,
                       fontName='Helvetica-Bold', textColor=colors.HexColor('#e0f2fe')))]
    band = Table([[logo or '', inner]], colWidths=[26 * mm, P_W - 26 * mm]) if logo is not None \
        else Table([[inner]], colWidths=[P_W])
    band.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), accent), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                              ('LEFTPADDING', (0, 0), (0, 0), 8), ('TOPPADDING', (0, 0), (-1, -1), 8),
                              ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
    above = [band, Spacer(1, 8)] + _fields([('Name', ctx['student'].full_name),
             ('Admission No.', ctx['student'].student_id), ('Sex', ctx['student'].gender),
             ('Graduation', ctx.get('grad_when'))], S) + [Spacer(1, 6)]
    sig = _sig(S)
    mid = _stmt_summary(ctx, rows, is_ssce, S) + [Spacer(1, 8)] + _grade_key(S, ssce=is_ssce) + _remarks(ctx, S)
    if not rows:
        return _page_fill(above + [Paragraph('No results are on record.', S['body'])], sig, avail=avail)
    return _page_fill(above + [_main_table(rows, is_ssce, S, accent, pad=5)] + mid, sig, avail=avail)


def _t_executive(ctx):
    """Minimalist executive statement: large wordmark, boxed two-column bio."""
    S = _styles()
    accent = colors.HexColor('#111827')
    rows, is_ssce, year = _statement_rows(ctx)
    avail = ctx.get('_avail', _P_BODY_H)
    name, addr, contact = _tt._header_lines(ctx['school'])
    above = [Paragraph(_esc(name), ParagraphStyle('wm', parent=S['left'], fontSize=19,
                       fontName='Helvetica-Bold', textColor=accent, leading=22)),
             HRFlowable(width='100%', thickness=1.4, color=accent), Spacer(1, 2),
             Paragraph('STATEMENT OF RESULT', ParagraphStyle('t', parent=S['left'], fontSize=11,
                       fontName='Helvetica-Bold', textColor=colors.HexColor('#475569'), spaceAfter=6))]
    info = [Paragraph(f"<b>Name:</b> {_esc(ctx['student'].full_name)}", S['left']),
            Paragraph(f"<b>Admission No.:</b> {_esc(ctx['student'].student_id)} &nbsp; "
                      f"<b>Sex:</b> {_esc(ctx['student'].gender)}", S['left']),
            Paragraph(f"<b>Graduation:</b> {_esc(ctx.get('grad_when'))}", S['left'])]
    box = Table([[info]], colWidths=[P_W])
    box.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.6, accent), ('LEFTPADDING', (0, 0), (-1, -1), 8),
                             ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    above += [box, Spacer(1, 8)]
    sig = _sig(S)
    mid = _stmt_summary(ctx, rows, is_ssce, S) + [Spacer(1, 8)] + _grade_key(S, ssce=is_ssce) + _remarks(ctx, S)
    if not rows:
        return _page_fill(above + [Paragraph('No results are on record.', S['body'])], sig, avail=avail)
    return _page_fill(above + [_main_table(rows, is_ssce, S, accent, pad=5)] + mid, sig, avail=avail)


def _t_crested(ctx):
    """Centred crested statement inside a gold ornate border."""
    S = _styles()
    accent = colors.HexColor('#713f12')
    rows, is_ssce, year = _statement_rows(ctx)
    avail = ctx.get('_avail', _P_BODY_H)
    name, addr, contact = _tt._header_lines(ctx['school'])
    above = _logo_center() + [
        Paragraph(_esc(name), ParagraphStyle('nm', parent=S['center'], fontSize=17, leading=20,
                  fontName='Helvetica-Bold', textColor=accent, spaceAfter=2))]
    if ctx['school'].get('motto'):
        above.append(Paragraph(f"<i>{_esc(ctx['school'].get('motto'))}</i>", S['center']))
    pill = Table([[Paragraph('STATEMENT OF RESULT', ParagraphStyle('p', parent=S['center'],
                  fontSize=12, fontName='Helvetica-Bold', textColor=colors.white))]], colWidths=[80 * mm])
    pill.hAlign = 'CENTER'
    pill.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), accent), ('TOPPADDING', (0, 0), (-1, -1), 4),
                              ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    above += [Spacer(1, 6), pill, Spacer(1, 8)] + _fields([('Name', ctx['student'].full_name),
             ('Admission No.', ctx['student'].student_id), ('Graduation', ctx.get('grad_when'))], S) + [Spacer(1, 6)]
    sig = _sig(S)
    mid = _stmt_summary(ctx, rows, is_ssce, S) + [Spacer(1, 8)] + _grade_key(S, ssce=is_ssce) + _remarks(ctx, S)
    if not rows:
        return _page_fill(above + [Paragraph('No results are on record.', S['body'])], sig, avail=avail)
    return _page_fill(above + [_main_table(rows, is_ssce, S, accent, pad=5)] + mid, sig, avail=avail)


def _t_ledger(ctx):
    """Ledger style: boxed bio grid + a heavier results table, inside a thin frame."""
    S = _styles()
    accent = colors.HexColor('#334155')
    rows, is_ssce, year = _statement_rows(ctx)
    avail = ctx.get('_avail', _P_BODY_H)
    above = _letterhead(ctx, accent, S)
    above += [Spacer(1, 4), Paragraph('STATEMENT OF RESULT', ParagraphStyle('ti', parent=S['center'],
              fontSize=14, fontName='Helvetica-Bold', textColor=accent, spaceBefore=4, spaceAfter=8))]
    bio = [[Paragraph(f"<b>Name:</b> {_esc(ctx['student'].full_name)}", S['left']),
            Paragraph(f"<b>Admission No.:</b> {_esc(ctx['student'].student_id)}", S['left'])],
           [Paragraph(f"<b>Sex:</b> {_esc(ctx['student'].gender)}", S['left']),
            Paragraph(f"<b>Graduation:</b> {_esc(ctx.get('grad_when'))}", S['left'])]]
    biot = Table(bio, colWidths=[P_W / 2, P_W / 2])
    biot.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                              ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                              ('LEFTPADDING', (0, 0), (-1, -1), 6)]))
    above += [biot, Spacer(1, 8)]
    sig = _sig(S)
    mid = _stmt_summary(ctx, rows, is_ssce, S) + [Spacer(1, 8)] + _grade_key(S, ssce=is_ssce) + _remarks(ctx, S)
    if not rows:
        return _page_fill(above + [Paragraph('No results are on record.', S['body'])], sig, avail=avail)
    return _page_fill(above + [_main_table(rows, is_ssce, S, accent, pad=5)] + mid, sig, avail=avail)


SOR_TEMPLATES = {
    'classic': {'name': 'Classic (default)', 'render': _t_classic,
                'description': 'Clean statement with an aggregated subject/score/grade table and grading key.'},
    'official': {'name': 'Official (boxed)', 'render': _t_official,
                 'description': 'Boxed official statement with a student-info panel and results table.'},
    'institutional': {'name': 'Examination Results', 'render': _t_institutional,
                      'description': 'Institutional “Statement of Examination Results”: dark banner, results table, credits/passed summary and registrar line.'},
    'waec': {'name': 'SSCE (blue border)', 'render': _t_waec, 'decorator': _border_blue,
             'description': 'WAEC/NECO-style SSCE statement in an ornate blue border, driven by the WAEC result when available.'},
    'bordered': {'name': 'SSCE (green border)', 'render': _t_bordered, 'decorator': _border_green,
                 'description': 'Community-school-style statement in a green dotted border with subjects, grades and remarks.'},
    'sessional': {'name': 'Per-session', 'render': _t_sessional,
                  'description': 'Results broken down by senior-secondary session (SS1–SS3).'},
    'modern': {'name': 'Modern Banner', 'render': _t_modern,
               'description': 'Coloured header bar with an aggregated results table and grading key.'},
    'banded': {'name': 'Masthead', 'render': _t_banded,
               'description': 'Full-width colour masthead with the school identity reversed out.'},
    'executive': {'name': 'Executive', 'render': _t_executive,
                  'description': 'Minimalist wordmark statement with a boxed bio panel.'},
    'crested': {'name': 'Crested (gold border)', 'render': _t_crested, 'decorator': _border_gold,
                'description': 'Centred crested statement inside a gold ornate border.'},
    'ledger': {'name': 'Ledger', 'render': _t_ledger, 'decorator': _thin_frame,
               'description': 'Boxed bio grid and a ruled results ledger inside a thin frame.'},
    'eagle': {'name': 'Crested SSCE (green border)', 'render': _t_eagle, 'decorator': _eagle_frame,
              'description': 'Crested two-tone masthead with a passport box, bio grid, subject/grade/remark '
                             'table, distinctions summary and a red result number (Eagle’s-Nest style).'},
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
