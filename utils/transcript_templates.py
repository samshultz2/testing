"""Transcript design templates (Phase 2 — document design).

Each template is a faithful layout inspired by real Nigerian secondary-school
transcripts. All designs are driven by the SAME data — the school's stored
internal per-term results (from ``utils.graduate_record.build_record``) — so a
school only chooses how the transcript LOOKS; the numbers are always their own.

A template's ``render(ctx)`` returns a list of reportlab flowables (the full
transcript body: letterhead, header fields, results grid, grading key,
signatures). The shared verification footer (QR + code) is appended by
``utils.graduate_docs.render`` so every design stays verifiable.

Register a new design by adding an entry to ``TRANSCRIPT_TEMPLATES``.
"""
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, HRFlowable

USABLE_W = 170 * mm            # A4 (210mm) minus 20mm margins each side


def _esc(v):
    from utils.web_exports import pdf_escape
    return pdf_escape(str(v if v is not None else ''))


def _grade(score):
    if score is None:
        return ''
    try:
        s = float(score)
    except (TypeError, ValueError):
        return ''
    return 'A' if s >= 70 else 'B' if s >= 60 else 'C' if s >= 50 else 'D' if s >= 40 else 'F'


def _fmt(v):
    if v is None:
        return '—'
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _styles():
    ss = getSampleStyleSheet()
    return {
        'body': ParagraphStyle('b', parent=ss['Normal'], fontSize=10.5, leading=16,
                               alignment=TA_JUSTIFY, spaceAfter=6),
        'left': ParagraphStyle('l', parent=ss['Normal'], fontSize=10, leading=15),
        'center': ParagraphStyle('c', parent=ss['Normal'], alignment=TA_CENTER, fontSize=10),
        'small': ParagraphStyle('s', parent=ss['Normal'], fontSize=8, textColor=colors.HexColor('#64748b')),
        'cell': ParagraphStyle('cell', parent=ss['Normal'], fontSize=7.5, leading=9),
        'cellc': ParagraphStyle('cellc', parent=ss['Normal'], fontSize=7.5, leading=9, alignment=TA_CENTER),
    }


# ---------------------------------------------------------------------------
# data shaping — one pivot shared by every design
# ---------------------------------------------------------------------------
def _matrix(academic):
    """Pivot per-term results into subject × (session, term) with per-session
    aggregates. Returns a dict the templates consume."""
    terms = (academic or {}).get('terms') or []
    sessions = []
    for t in terms:
        if t.get('session') and t['session'] not in sessions:
            sessions.append(t['session'])
    sessions.sort()
    term_nums = sorted({t.get('term_number') or 0 for t in terms if t.get('term_number')}) or [1, 2, 3]
    subjects = []
    grid = {}
    for t in terms:
        for s in t.get('subjects') or []:
            name = s.get('subject') or 'Subject'
            if name not in subjects:
                subjects.append(name)
            grid.setdefault(name, {})[(t['session'], t.get('term_number') or 0)] = s
    subjects.sort()
    # per (subject, session) average across that session's terms
    sess_scores = {}
    for name in subjects:
        for sess in sessions:
            vals = [grid[name][(sess, tn)].get('score') for tn in term_nums
                    if (sess, tn) in grid.get(name, {}) and grid[name][(sess, tn)].get('score') is not None]
            if vals:
                sess_scores[(name, sess)] = round(sum(vals) / len(vals), 1)
    ss_labels = {sess: f'SS {i + 1}' for i, sess in enumerate(sessions)}
    return {
        'sessions': sessions, 'ss_labels': ss_labels, 'term_nums': term_nums,
        'subjects': subjects, 'grid': grid, 'sess_scores': sess_scores,
        'cumulative': (academic or {}).get('cumulative'),
    }


def _header_lines(school):
    """(name, address, contact) tuple for a letterhead."""
    contact = ' · '.join([x for x in [school.get('phone'), school.get('email')] if x])
    return school.get('name') or 'School', school.get('address') or '', contact


def _logo():
    try:
        from utils.school import logo_flowable
        return logo_flowable(max_h_mm=18, max_w_mm=28)
    except Exception:
        return None


def _letterhead(ctx, accent, centered=True):
    """A logo + school name/address band used by several designs."""
    S = _styles()
    name, addr, contact = _header_lines(ctx['school'])
    nm = ParagraphStyle('nm', parent=S['center'] if centered else S['left'],
                        fontSize=16, leading=19, textColor=accent, fontName='Helvetica-Bold')
    sub = ParagraphStyle('sub', parent=S['center'] if centered else S['left'],
                         fontSize=8.5, textColor=colors.HexColor('#475569'))
    lines = [Paragraph(_esc(name), nm)]
    if addr:
        lines.append(Paragraph(_esc(addr), sub))
    if contact:
        lines.append(Paragraph(_esc('Tel: ' + contact), sub))
    logo = _logo()
    if logo is not None:
        t = Table([[logo, lines]], colWidths=[30 * mm, USABLE_W - 30 * mm])
        t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                               ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
        return [t]
    return lines


def _header_fields(pairs, S):
    """A two-column 'Label: value' block."""
    rows = [[Paragraph(f'<b>{_esc(k)}</b>', S['left']), Paragraph(_esc(v), S['left'])]
            for k, v in pairs if v]
    if not rows:
        return []
    t = Table(rows, colWidths=[42 * mm, USABLE_W - 42 * mm])
    t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                           ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                           ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
    return [t]


def _grade_key(S, style='mark'):
    data = [['MARK', 'GRADE', 'REMARK'],
            ['70 – 100', 'A', 'Distinction'], ['60 – 69', 'B', 'Very good'],
            ['50 – 59', 'C', 'Good'], ['40 – 49', 'D', 'Pass'], ['0 – 39', 'F', 'Fail']]
    t = Table(data, colWidths=[30 * mm, 20 * mm, 40 * mm])
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
    return [Paragraph('<b>Key to grading</b>', S['small']), Spacer(1, 3), t]


def _signatures(S, labels=('Principal', 'Registrar')):
    cells, subs = [], []
    for lab in labels:
        cells.append('_' * 24)
        subs.append(Paragraph(f'<b>{_esc(lab)}</b>', S['small']))
    gap = (USABLE_W - len(labels) * 55 * mm)
    widths = [55 * mm] * len(labels)
    t = Table([cells, subs], colWidths=widths, hAlign='LEFT')
    t.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('TOPPADDING', (0, 1), (-1, 1), 2)]))
    return [Spacer(1, 22), t]


def _term_grid(m, S, accent, show_grades=False):
    """Wide grid: SUBJECT × (each session grouped into its terms). Optionally a
    grade sub-column. Includes an Average row."""
    sessions, tnums = m['sessions'], m['term_nums']
    ncols = len(sessions) * len(tnums)
    subj_w = 38 * mm
    col_w = max(9 * mm, (USABLE_W - subj_w) / max(1, ncols))
    # header rows
    top = ['SUBJECT']
    for sess in sessions:
        top += [m['ss_labels'][sess]] + [''] * (len(tnums) - 1)
    sub = ['']
    tlabels = {1: '1st', 2: '2nd', 3: '3rd'}
    for _ in sessions:
        for tn in tnums:
            sub.append(tlabels.get(tn, f'T{tn}'))
    rows = [top, sub]
    for name in m['subjects']:
        r = [Paragraph(_esc(name), S['cell'])]
        for sess in sessions:
            for tn in tnums:
                cell = m['grid'].get(name, {}).get((sess, tn))
                r.append(_fmt(cell.get('score')) if cell else '—')
        rows.append(r)
    # average row
    avg_row = ['Average']
    for sess in sessions:
        for tn in tnums:
            vals = [m['grid'][s2][(sess, tn)].get('score') for s2 in m['subjects']
                    if (sess, tn) in m['grid'].get(s2, {}) and m['grid'][s2][(sess, tn)].get('score') is not None]
            avg_row.append(str(round(sum(vals) / len(vals), 1)) if vals else '—')
    rows.append(avg_row)

    t = Table(rows, colWidths=[subj_w] + [col_w] * ncols, repeatRows=2)
    style = [
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('FONTNAME', (0, 0), (-1, 1), 'Helvetica-Bold'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 1), accent), ('TEXTCOLOR', (0, 0), (-1, 1), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#94a3b8')),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e2e8f0')),
    ]
    # span the session group headers across their term columns
    c = 1
    for _ in sessions:
        if len(tnums) > 1:
            style.append(('SPAN', (c, 0), (c + len(tnums) - 1, 0)))
        c += len(tnums)
    # merge the SUBJECT header cell down two rows
    style.append(('SPAN', (0, 0), (0, 1)))
    t.setStyle(TableStyle(style))
    return t


def _year_grid(m, S, accent):
    """Compact grid: S/N · SUBJECT × per-session (Score + Grade)."""
    sessions = m['sessions']
    head1 = ['S/N', 'SUBJECT']
    for sess in sessions:
        head1 += [m['ss_labels'].get(sess, sess)] + ['']
    head2 = ['', '']
    for _ in sessions:
        head2 += ['Score', 'Grade']
    rows = [head1, head2]
    for i, name in enumerate(m['subjects'], 1):
        r = [str(i), Paragraph(_esc(name), S['cell'])]
        for sess in sessions:
            sc = m['sess_scores'].get((name, sess))
            r += [_fmt(sc), _grade(sc)]
        rows.append(r)
    sn_w, subj_w = 10 * mm, 46 * mm
    pair_w = (USABLE_W - sn_w - subj_w) / max(1, len(sessions))
    widths = [sn_w, subj_w] + [pair_w / 2, pair_w / 2] * len(sessions)
    t = Table(rows, colWidths=widths, repeatRows=2)
    style = [
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('FONTNAME', (0, 0), (-1, 1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 1), accent), ('TEXTCOLOR', (0, 0), (-1, 1), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#94a3b8')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'), ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
    ]
    style.append(('SPAN', (0, 0), (0, 1)))
    style.append(('SPAN', (1, 0), (1, 1)))
    c = 2
    for _ in sessions:
        style.append(('SPAN', (c, 0), (c + 1, 0)))
        c += 2
    t.setStyle(TableStyle(style))
    return t


def _no_results(S):
    return [Paragraph('No internal academic results are on record for this student.', S['body'])]


# ---------------------------------------------------------------------------
# templates
# ---------------------------------------------------------------------------
def _t_classic(ctx):
    """Clean, modern default — accent title band + per-year score/grade grid."""
    S = _styles()
    accent = colors.HexColor('#0e8a64')
    m = _matrix(ctx['academic'])
    el = _letterhead(ctx, colors.HexColor('#0e3a2f'))
    el += [Spacer(1, 4), HRFlowable(width='100%', thickness=1, color=accent)]
    title = ParagraphStyle('ti', parent=S['center'], fontSize=14, textColor=accent,
                           fontName='Helvetica-Bold', spaceBefore=6, spaceAfter=8)
    el.append(Paragraph('ACADEMIC TRANSCRIPT', title))
    el += _header_fields([
        ('Name', ctx['student'].full_name), ('Admission No.', ctx['student'].student_id),
        ('Sex', ctx['student'].gender), ('Graduation', ctx['grad_when']),
        ('Cumulative Average', f"{m['cumulative']}%" if m['cumulative'] is not None else None),
    ], S)
    el.append(Spacer(1, 8))
    el.append(_year_grid(m, S, accent) if m['subjects'] else Paragraph('No internal results are on record.', S['body']))
    el.append(Spacer(1, 10))
    el += _grade_key(S)
    el += _signatures(S)
    return el


def _t_verbins(ctx):
    """'To Whom It May Concern' letter + wide cumulative per-term grid."""
    S = _styles()
    accent = colors.HexColor('#b91c1c')
    m = _matrix(ctx['academic'])
    el = _letterhead(ctx, colors.HexColor('#1e3a8a'))
    el += [Spacer(1, 4), HRFlowable(width='100%', thickness=1.4, color=accent), Spacer(1, 8)]
    title = ParagraphStyle('ti', parent=S['center'], fontSize=13, fontName='Helvetica-Bold', spaceAfter=8)
    el.append(Paragraph('TO WHOM IT MAY CONCERN', title))
    name = ctx['student'].full_name
    el.append(Paragraph(
        f"This is to certify that <b>{_esc(name)}</b> (Admission No. {_esc(ctx['student'].student_id)}) "
        f"was a student of <b>{_esc(ctx['school'].get('name') or 'this school')}</b>. Below is "
        f"{'his' if (ctx['student'].gender or '').lower().startswith('m') else 'her' if (ctx['student'].gender or '').lower().startswith('f') else 'their'} "
        f"transcript for senior secondary school (SS1 – SS3).", S['body']))
    el.append(Spacer(1, 6))
    hd = ParagraphStyle('hd', parent=S['center'], fontSize=10, fontName='Helvetica-Bold',
                        textColor=colors.white, backColor=accent, spaceAfter=0)
    el.append(Table([[Paragraph('CUMULATIVE SENIOR SECONDARY RESULT', hd)]], colWidths=[USABLE_W],
                    style=TableStyle([('BACKGROUND', (0, 0), (-1, -1), accent),
                                      ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)])))
    el.append(_term_grid(m, S, accent) if m['subjects'] else Paragraph('No internal results are on record.', S['body']))
    if m['cumulative'] is not None:
        el.append(Spacer(1, 4))
        el.append(Paragraph(f"<b>Cumulative Average:</b> {m['cumulative']}%", S['left']))
    el.append(Spacer(1, 10))
    el += _grade_key(S)
    el += _signatures(S, labels=('Exam Officer', 'Principal'))
    return el


def _t_nawair(ctx):
    """Recipient-addressed transcript with a per-term SUBJECT grid."""
    S = _styles()
    accent = colors.HexColor('#166534')
    m = _matrix(ctx['academic'])
    el = _letterhead(ctx, accent)
    el += [Spacer(1, 4), HRFlowable(width='100%', thickness=1.2, color=accent), Spacer(1, 6)]
    from datetime import date
    issued = (ctx['doc'].created_at.strftime('%d/%m/%Y') if ctx.get('doc') and ctx['doc'].created_at
              else date.today().strftime('%d/%m/%Y'))
    el.append(Paragraph(f"Date: {issued}", S['left']))
    el.append(Paragraph("To Whom It May Concern,", S['left']))
    el.append(Spacer(1, 6))
    title = ParagraphStyle('ti', parent=S['center'], fontSize=13, fontName='Helvetica-Bold', spaceAfter=8)
    el.append(Paragraph('SCHOOL TRANSCRIPT', title))
    el += _header_fields([
        ('Name', ctx['student'].full_name), ('Registration No.', ctx['student'].student_id),
        ('Sex', ctx['student'].gender),
        ('Admission', ctx.get('admission_session')), ('Graduation Date', ctx['grad_when']),
        ('Date Issued', issued),
    ], S)
    el.append(Spacer(1, 8))
    el.append(_term_grid(m, S, accent) if m['subjects'] else Paragraph('No internal results are on record.', S['body']))
    el.append(Spacer(1, 8))
    el.append(Paragraph("This is to certify that the above-mentioned information is true and correct.", S['body']))
    el += _signatures(S, labels=('Principal',))
    return el


def _t_ohis(ctx):
    """'RE: name' summary with an S/N score+grade year grid and grading key."""
    S = _styles()
    accent = colors.HexColor('#0f766e')
    m = _matrix(ctx['academic'])
    el = _letterhead(ctx, accent)
    el += [Spacer(1, 4), HRFlowable(width='100%', thickness=1.2, color=accent), Spacer(1, 6)]
    title = ParagraphStyle('ti', parent=S['center'], fontSize=13, fontName='Helvetica-Bold', spaceAfter=4)
    el.append(Paragraph('SCHOOL TRANSCRIPT', title))
    el.append(Paragraph(f"RE: <b>{_esc(ctx['student'].full_name)}</b>", S['center']))
    el.append(Spacer(1, 6))
    el += _header_fields([
        ('Admission No.', ctx['student'].student_id), ('Sex', ctx['student'].gender),
        ('Graduation', ctx['grad_when']),
    ], S)
    el.append(Paragraph(
        f"Find below the summary of the academic performance of the above-named student of "
        f"<b>{_esc(ctx['school'].get('name') or 'this school')}</b>.", S['body']))
    el.append(Spacer(1, 6))
    el.append(_year_grid(m, S, accent) if m['subjects'] else Paragraph('No internal results are on record.', S['body']))
    el.append(Spacer(1, 8))
    el += _grade_key(S)
    el.append(Spacer(1, 6))
    el.append(Paragraph("I affirm that the above record is a true reflection of the student's performance.", S['body']))
    el += _signatures(S, labels=('Principal',))
    return el


def _t_govsci(ctx):
    """'Official High School Transcript' — boxed student/school panels + a
    per-session academic record."""
    S = _styles()
    accent = colors.HexColor('#1f2937')
    m = _matrix(ctx['academic'])
    hdr = ParagraphStyle('h', parent=S['center'], fontSize=12, fontName='Helvetica-Bold')
    el = [Table([[Paragraph('OFFICIAL HIGH SCHOOL TRANSCRIPT', hdr)]], colWidths=[USABLE_W],
                style=TableStyle([('BOX', (0, 0), (-1, -1), 1, accent),
                                  ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))]
    el.append(Spacer(1, 6))
    stu = [Paragraph('<b>STUDENT INFORMATION</b>', S['small']),
           Paragraph(f"<b>Name:</b> {_esc(ctx['student'].full_name)}", S['left']),
           Paragraph(f"<b>Admission No.:</b> {_esc(ctx['student'].student_id)}", S['left']),
           Paragraph(f"<b>Sex:</b> {_esc(ctx['student'].gender)}", S['left']),
           Paragraph(f"<b>Graduation:</b> {_esc(ctx['grad_when'])}", S['left'])]
    name, addr, contact = _header_lines(ctx['school'])
    sch = [Paragraph('<b>SCHOOL INFORMATION</b>', S['small']),
           Paragraph(f"<b>Name:</b> {_esc(name)}", S['left'])]
    if addr:
        sch.append(Paragraph(f"<b>Address:</b> {_esc(addr)}", S['left']))
    if contact:
        sch.append(Paragraph(f"<b>Contact:</b> {_esc(contact)}", S['left']))
    panels = Table([[stu, sch]], colWidths=[USABLE_W / 2, USABLE_W / 2])
    panels.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.6, accent),
                                ('INNERGRID', (0, 0), (-1, -1), 0.6, accent),
                                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                                ('LEFTPADDING', (0, 0), (-1, -1), 8)]))
    el += [panels, Spacer(1, 8),
           Table([[Paragraph('ACADEMIC RECORD', hdr)]], colWidths=[USABLE_W],
                 style=TableStyle([('BOX', (0, 0), (-1, -1), 0.8, accent),
                                   ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)])),
           Spacer(1, 6)]
    if not m['subjects']:
        return el + _no_results(S) + _signatures(S, labels=('Principal',))
    # one block per session
    for sess in m['sessions']:
        cap = ParagraphStyle('cap', parent=S['small'], fontName='Helvetica-Bold', textColor=accent)
        el.append(Paragraph(f"{m['ss_labels'].get(sess, sess)} — {_esc(sess)}", cap))
        rows = [['Course Title', 'Score', 'Grade', 'Remark']]
        for name2 in m['subjects']:
            sc = m['sess_scores'].get((name2, sess))
            if sc is None:
                continue
            g = _grade(sc)
            remark = {'A': 'Excellent', 'B': 'Very good', 'C': 'Good', 'D': 'Pass', 'F': 'Fail'}.get(g, '')
            rows.append([Paragraph(_esc(name2), S['cell']), _fmt(sc), g, remark])
        t = Table(rows, colWidths=[80 * mm, 25 * mm, 25 * mm, 40 * mm], repeatRows=1)
        t.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 8), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#94a3b8')),
            ('ALIGN', (1, 0), (2, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
        el += [t, Spacer(1, 6)]
    el += _signatures(S, labels=('Principal',))
    return el


def _t_modern(ctx):
    """A contemporary card layout: accent header bar, KPI line, per-term grid."""
    S = _styles()
    accent = colors.HexColor('#4338ca')
    m = _matrix(ctx['academic'])
    name, addr, contact = _header_lines(ctx['school'])
    bar_name = ParagraphStyle('bn', parent=S['left'], fontSize=15, fontName='Helvetica-Bold', textColor=colors.white)
    bar_sub = ParagraphStyle('bs', parent=S['left'], fontSize=8, textColor=colors.HexColor('#e0e7ff'))
    bar_inner = [Paragraph(_esc(name), bar_name)]
    if addr:
        bar_inner.append(Paragraph(_esc(addr), bar_sub))
    if contact:
        bar_inner.append(Paragraph(_esc(contact), bar_sub))
    bar = Table([[bar_inner, Paragraph('ACADEMIC<br/>TRANSCRIPT', ParagraphStyle(
        'bt', parent=S['left'], fontSize=12, fontName='Helvetica-Bold', textColor=colors.white, alignment=2))]],
        colWidths=[USABLE_W - 45 * mm, 45 * mm])
    bar.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), accent),
                             ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                             ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                             ('LEFTPADDING', (0, 0), (0, 0), 10), ('RIGHTPADDING', (-1, -1), (-1, -1), 10)]))
    el = [bar, Spacer(1, 8)]
    el += _header_fields([
        ('Name', ctx['student'].full_name), ('Admission No.', ctx['student'].student_id),
        ('Sex', ctx['student'].gender), ('Graduation', ctx['grad_when']),
        ('Cumulative Average', f"{m['cumulative']}%" if m['cumulative'] is not None else None),
    ], S)
    el.append(Spacer(1, 8))
    el.append(_term_grid(m, S, accent) if m['subjects'] else Paragraph('No internal results are on record.', S['body']))
    el.append(Spacer(1, 10))
    el += _grade_key(S)
    el += _signatures(S)
    return el


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
TRANSCRIPT_TEMPLATES = {
    'classic': {'name': 'Classic (default)', 'render': _t_classic,
                'description': 'Clean modern layout with a per-year score & grade grid and grading key.'},
    'verbins': {'name': 'Formal Letter', 'render': _t_verbins,
                'description': '“To Whom It May Concern” letter with a wide cumulative SS1–SS3 per-term grid.'},
    'nawair': {'name': 'Addressed Transcript', 'render': _t_nawair,
               'description': 'Recipient-dated transcript with header fields and a per-term subject grid.'},
    'ohis': {'name': 'Summary Sheet', 'render': _t_ohis,
             'description': '“RE:” summary with a numbered subject list, per-year score/grade and grading key.'},
    'govsci': {'name': 'Official (Boxed)', 'render': _t_govsci,
               'description': 'Boxed student & school panels with a per-session academic record.'},
    'modern': {'name': 'Modern Banner', 'render': _t_modern,
               'description': 'Contemporary coloured header bar with a per-term results grid.'},
}

DEFAULT_TEMPLATE = 'classic'


def list_templates():
    return [{'key': k, 'name': v['name'], 'description': v['description']}
            for k, v in TRANSCRIPT_TEMPLATES.items()]


def resolve(key):
    return TRANSCRIPT_TEMPLATES.get(key) or TRANSCRIPT_TEMPLATES[DEFAULT_TEMPLATE]


def build_flowables(key, ctx):
    return resolve(key)['render'](ctx)


def sample_ctx(school):
    """A believable sample student + results so a design can be previewed even
    when the school has no graduate records yet."""
    from types import SimpleNamespace
    from datetime import date
    subjects = ['English Language', 'Mathematics', 'Biology', 'Chemistry', 'Physics',
                'Economics', 'Civic Education']
    sessions = ['2021/2022', '2022/2023', '2023/2024']
    terms = []
    base = 62
    for si, sess in enumerate(sessions):
        for tn in (1, 2, 3):
            subs = []
            for i, sub in enumerate(subjects):
                score = min(98, base + si * 4 + tn + (i % 5) * 3)
                subs.append({'subject': sub, 'score': score, 'grade': _grade(score),
                             'position': None, 'remark': None})
            avg = round(sum(s['score'] for s in subs) / len(subs), 1)
            terms.append({'term': f'Term {tn}', 'term_number': tn, 'session': sess,
                          'average': avg, 'subjects': subs})
    allscores = [s['score'] for t in terms for s in t['subjects']]
    academic = {'cumulative': round(sum(allscores) / len(allscores), 1),
                'terms_count': len(terms), 'terms': terms}
    student = SimpleNamespace(full_name='Adaeze N. Okoro (SAMPLE)', student_id='STU-SAMPLE',
                              gender='Female', graduation_date=date(2024, 7, 1))
    return {'student': student, 'academic': academic, 'bio': {}, 'school': school,
            'grad_when': 'July 2024', 'grad_session': '2023/2024',
            'admission_session': '2021/2022', 'doc': None}
