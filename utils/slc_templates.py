"""School Leaving Certificate design templates (Phase 2 — document design).

Like the transcript templates, each design is driven by the same data (the
graduate's record) — only the look changes. A design's ``render(ctx)`` returns a
list of reportlab flowables; a design may declare ``landscape=True`` and an
optional canvas ``decorator`` (a printed border / background). The shared
verification footer (QR + code) is appended by ``utils.graduate_docs.render``.
"""
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.graphics.shapes import Drawing, Circle, String, Polygon

# Usable content width = page - margins - the frame's 6pt padding on each side.
P_W = 165 * mm                       # portrait  (A4 210mm - 20mm margins - padding)
L_W = 255 * mm                       # landscape (A4 297mm - 18mm margins - padding)


def _esc(v):
    from utils.web_exports import pdf_escape
    return pdf_escape(str(v if v is not None else ''))


def _styles():
    ss = getSampleStyleSheet()
    return {
        'body': ParagraphStyle('b', parent=ss['Normal'], fontSize=11, leading=18,
                               alignment=TA_JUSTIFY, spaceAfter=6),
        'bodyc': ParagraphStyle('bc', parent=ss['Normal'], fontSize=11, leading=18,
                                alignment=TA_CENTER, spaceAfter=6),
        'left': ParagraphStyle('l', parent=ss['Normal'], fontSize=10.5, leading=20),
        'center': ParagraphStyle('c', parent=ss['Normal'], alignment=TA_CENTER, fontSize=10.5),
        'small': ParagraphStyle('s', parent=ss['Normal'], fontSize=8, textColor=colors.HexColor('#64748b')),
    }


def _logo(max_h=18, max_w=26):
    try:
        from utils.school import logo_flowable
        return logo_flowable(max_h_mm=max_h, max_w_mm=max_w)
    except Exception:
        return None


def _header_lines(school):
    contact = ' · '.join([x for x in [school.get('phone'), school.get('email')] if x])
    return school.get('name') or 'School', school.get('address') or '', contact


def _seal(dia=20, text='OFFICIAL SEAL'):
    d = Drawing(dia * mm, dia * mm)
    r = dia * mm / 2
    d.add(Circle(r, r, r, fillColor=colors.HexColor('#b7791f'), strokeColor=colors.HexColor('#7c5210'), strokeWidth=1.4))
    d.add(Circle(r, r, r - 2.4, fillColor=None, strokeColor=colors.white, strokeWidth=0.8))
    d.add(String(r, r - 2, text, textAnchor='middle', fontSize=4.4, fillColor=colors.white, fontName='Helvetica-Bold'))
    return d


def _fill(label, value, S, w_label=46 * mm, total=P_W):
    """A labelled fill-in line: the value sits on an underline (drawn as a cell
    border so long values wrap cleanly instead of overflowing)."""
    lab = Paragraph(f"<b>{_esc(label)}</b>", S['left']) if label else Paragraph('&nbsp;', S['left'])
    val = Paragraph(_esc(value) or '&nbsp;', S['left'])
    t = Table([[lab, val]], colWidths=[w_label, total - w_label])
    t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'BOTTOM'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                           ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                           ('LINEBELOW', (1, 0), (1, 0), 0.6, colors.HexColor('#94a3b8'))]))
    return t


def _sig_row(labels, width, S, seal=False):
    """Signature blocks spread across the page, optional centre seal."""
    n = len(labels)
    if seal and n == 2:
        cells = [[Paragraph('_' * 22, S['center']), _seal(), Paragraph('_' * 22, S['center'])],
                 [Paragraph(f"<b>{_esc(labels[0])}</b>", S['small']), '',
                  Paragraph(f"<b>{_esc(labels[1])}</b>", S['small'])]]
        colw = [(width - 26 * mm) / 2, 26 * mm, (width - 26 * mm) / 2]
    else:
        cells = [[Paragraph('_' * 22, S['center']) for _ in labels],
                 [Paragraph(f"<b>{_esc(l)}</b>", S['small']) for l in labels]]
        colw = [width / n] * n
    t = Table(cells, colWidths=colw)
    t.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                           ('TOPPADDING', (0, 1), (-1, 1), 2)]))
    return t


def _career_line(ctx):
    return f"from {_esc(ctx.get('from_year') or '—')} to {_esc(ctx.get('to_year') or '—')}"


# ---------------------------------------------------------------------------
# decorators (printed borders / backgrounds)
# ---------------------------------------------------------------------------
def _border_floral(canvas, doc):
    w, h = doc.pagesize
    red = colors.HexColor('#b91c1c')
    canvas.saveState()
    for i, m in enumerate((10 * mm, 13 * mm)):
        canvas.setStrokeColor(red)
        canvas.setLineWidth(3 if i == 0 else 1)
        canvas.rect(m, m, w - 2 * m, h - 2 * m, stroke=1, fill=0)
    canvas.setFillColor(red)
    step = 12 * mm
    x = 16 * mm
    while x < w - 16 * mm:
        for y in (11.5 * mm, h - 11.5 * mm):
            canvas.circle(x, y, 1.1 * mm, fill=1, stroke=0)
        x += step
    y = 16 * mm
    while y < h - 16 * mm:
        for x2 in (11.5 * mm, w - 11.5 * mm):
            canvas.circle(x2, y, 1.1 * mm, fill=1, stroke=0)
        y += step
    canvas.restoreState()


def _border_gold(canvas, doc):
    w, h = doc.pagesize
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor('#b7791f'))
    canvas.setLineWidth(4)
    canvas.rect(9 * mm, 9 * mm, w - 18 * mm, h - 18 * mm, stroke=1, fill=0)
    canvas.setLineWidth(1)
    canvas.rect(12 * mm, 12 * mm, w - 24 * mm, h - 24 * mm, stroke=1, fill=0)
    canvas.restoreState()


def _bg_corners_blue(canvas, doc):
    """Blue + gold angular corner blocks (BOSS / modern style)."""
    w, h = doc.pagesize
    navy = colors.HexColor('#1e3a8a')
    gold = colors.HexColor('#c99700')
    canvas.saveState()
    canvas.setFillColor(navy)
    canvas.setStrokeColor(navy)
    canvas.drawPath(_poly(canvas, [(0, h), (70 * mm, h), (0, h - 55 * mm)]), fill=1, stroke=0)
    canvas.drawPath(_poly(canvas, [(w, 0), (w - 70 * mm, 0), (w, 55 * mm)]), fill=1, stroke=0)
    canvas.setFillColor(gold)
    canvas.drawPath(_poly(canvas, [(0, h), (52 * mm, h), (0, h - 40 * mm)]), fill=1, stroke=0)
    canvas.drawPath(_poly(canvas, [(w, 0), (w - 52 * mm, 0), (w, 40 * mm)]), fill=1, stroke=0)
    canvas.setStrokeColor(navy)
    canvas.setLineWidth(1.5)
    canvas.rect(10 * mm, 10 * mm, w - 20 * mm, h - 20 * mm, stroke=1, fill=0)
    canvas.restoreState()


def _poly(canvas, pts):
    p = canvas.beginPath()
    p.moveTo(*pts[0])
    for x, y in pts[1:]:
        p.lineTo(x, y)
    p.close()
    return p


# ---------------------------------------------------------------------------
# templates
# ---------------------------------------------------------------------------
def _letterhead(ctx, accent, S):
    name, addr, contact = _header_lines(ctx['school'])
    nm = ParagraphStyle('nm', parent=S['center'], fontSize=17, leading=20, textColor=accent, fontName='Helvetica-Bold')
    sub = ParagraphStyle('sub', parent=S['center'], fontSize=8.5, textColor=colors.HexColor('#475569'))
    lines = [Paragraph(_esc(name), nm)]
    if addr:
        lines.append(Paragraph(_esc(addr), sub))
    if contact:
        lines.append(Paragraph(_esc('Tel: ' + contact), sub))
    logo = _logo()
    if logo is not None:
        t = Table([[logo, lines]], colWidths=[30 * mm, P_W - 30 * mm])
        t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
        return [t]
    return lines


def _t_classic(ctx):
    """Clean portrait certificate with a certifying paragraph."""
    S = _styles()
    accent = colors.HexColor('#0e3a2f')
    el = _letterhead(ctx, accent, S)
    el += [Spacer(1, 6), HRFlowable(width='100%', thickness=1.2, color=colors.HexColor('#0e8a64'))]
    el.append(Paragraph('SCHOOL LEAVING CERTIFICATE', ParagraphStyle(
        'ti', parent=S['center'], fontSize=15, fontName='Helvetica-Bold', textColor=colors.HexColor('#0e8a64'),
        spaceBefore=10, spaceAfter=12)))
    st = ctx['student']
    el.append(Paragraph(
        f"This is to certify that <b>{_esc(st.full_name)}</b> (Admission No. {_esc(st.student_id)}) "
        f"was a bona fide student of <b>{_esc(ctx['school'].get('name') or 'this school')}</b> "
        f"{_career_line(ctx)}, and completed the Senior Secondary programme in "
        f"{_esc(ctx.get('grad_when'))}.", S['body']))
    if ctx.get('subjects_list'):
        el.append(Paragraph(f"<b>Subjects studied:</b> {_esc(ctx['subjects_list'])}.", S['body']))
    if ctx.get('performance'):
        el.append(Paragraph(f"<b>Academic performance:</b> {_esc(ctx['performance'])}. "
                            f"<b>Character:</b> {_esc(ctx.get('character') or 'Satisfactory')}.", S['body']))
    el.append(Paragraph("We wish this student every success in their future endeavours.", S['body']))
    el += [Spacer(1, 26), _sig_row(['Principal', 'Registrar'], P_W, S)]
    return el


def _t_comprehensive(ctx):
    """Ornate fill-in 'School Leaving Certificate & Testimonial'."""
    S = _styles()
    accent = colors.HexColor('#b91c1c')
    el = _letterhead(ctx, colors.HexColor('#111827'), S)
    el.append(Paragraph('School Leaving Certificate &amp; Testimonial', ParagraphStyle(
        'ti', parent=S['center'], fontSize=17, fontName='Helvetica-BoldOblique', textColor=accent,
        spaceBefore=8, spaceAfter=6)))
    el.append(Paragraph('This is to Certify that', S['bodyc']))
    st = ctx['student']
    el.append(Paragraph(f"<b>{_esc(st.full_name)}</b>", ParagraphStyle(
        'nm', parent=S['center'], fontSize=14, fontName='Helvetica-Bold', spaceAfter=6)))
    el += [_fill('Born in', (ctx.get('bio') or {}).get('date_of_birth'), S),
           _fill('Was a Pupil of this School', '', S, w_label=64 * mm),
           _fill('From', ctx.get('from_year'), S), _fill('to', ctx.get('to_year'), S),
           _fill('And left in', ctx.get('to_year'), S),
           _fill('Academic performance', ctx.get('performance'), S),
           _fill('Subjects Studied Included', ctx.get('subjects_list'), S),
           _fill('Character', ctx.get('character') or 'Satisfactory', S),
           _fill('Extra Curricula Activities', '', S),
           _fill('Other Remarks', '', S)]
    el += [Spacer(1, 20), _sig_row(["Student's Signature", 'Principal'], P_W, S)]
    return el


def _t_record(ctx):
    """'Certificate of School Leaving' with a particulars table."""
    S = _styles()
    accent = colors.HexColor('#b91c1c')
    el = _letterhead(ctx, colors.HexColor('#111827'), S)
    el.append(Paragraph('CERTIFICATE OF SCHOOL LEAVING', ParagraphStyle(
        'ti', parent=S['center'], fontSize=16, fontName='Helvetica-Bold', spaceBefore=10, spaceAfter=10)))
    st = ctx['student']
    bio = ctx.get('bio') or {}
    el += [_fill('Admission No.', st.student_id, S), _fill('Name', st.full_name, S),
           _fill('Date of Birth', bio.get('date_of_birth'), S),
           _fill('Address', bio.get('home_address'), S)]
    el.append(Spacer(1, 4))
    el.append(Paragraph(
        f"Certified that the above-named student attended this school {_career_line(ctx)}, "
        f"was of good conduct, and left in good standing. The particulars below are certified "
        f"as produced from the school's records.", S['body']))
    rows = [['Date of Admission', 'Class', 'Date of Withdrawal', 'Academic Performance'],
            [_esc(ctx.get('from_year')), 'SS3', _esc(ctx.get('to_year')), _esc(ctx.get('performance') or '—')]]
    t = Table(rows, colWidths=[45 * mm, 25 * mm, 45 * mm, 55 * mm])
    t.setStyle(TableStyle([('FONTSIZE', (0, 0), (-1, -1), 9), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                           ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
                           ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#94a3b8')),
                           ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                           ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    el += [Spacer(1, 8), t, Spacer(1, 24), _sig_row(['Date of Issue', 'Principal'], P_W, S)]
    return el


def _cert_intro(ctx, S, title_color, name_font='Times-BoldItalic'):
    name = ParagraphStyle('nm', parent=S['center'], fontSize=26, leading=30,
                          fontName=name_font, textColor=title_color, spaceBefore=6, spaceAfter=6)
    return [Paragraph('This is to certify that', S['bodyc']),
            Paragraph(_esc(ctx['student'].full_name), name),
            HRFlowable(width='55%', thickness=0.6, color=colors.HexColor('#94a3b8'))]


def _t_awarded(ctx):
    """Landscape awarded certificate (BOSS style)."""
    S = _styles()
    navy = colors.HexColor('#1e3a8a')
    gold = colors.HexColor('#b7791f')
    name, _, _ = _header_lines(ctx['school'])
    el = [Spacer(1, 6),
          Paragraph('SCHOOL LEAVING CERTIFICATE', ParagraphStyle(
              'ti', parent=S['center'], fontSize=24, fontName='Helvetica-Bold', textColor=navy, spaceAfter=2)),
          Paragraph(_esc(name), ParagraphStyle('sn', parent=S['center'], fontSize=12, textColor=gold, spaceAfter=10)),
          Paragraph('This certificate is awarded to', S['bodyc'])]
    el.append(Paragraph(_esc(ctx['student'].full_name), ParagraphStyle(
        'nm', parent=S['center'], fontSize=26, fontName='Times-BoldItalic', textColor=colors.HexColor('#111827'),
        spaceBefore=4, spaceAfter=6)))
    el.append(Paragraph(
        f"A bona fide student of this school {_career_line(ctx)} who successfully completed the "
        f"senior secondary programme with good moral character, maintaining a good relationship with "
        f"teachers and peers.", ParagraphStyle('p', parent=S['bodyc'], fontSize=11, leading=17)))
    el.append(Paragraph(f"Given on {_esc(ctx.get('issued'))}.", S['bodyc']))
    el += [Spacer(1, 18), _sig_row(['Chairman, Board of Governors', 'Principal'], L_W, S, seal=True)]
    return el


def _t_vintage(ctx):
    """Landscape classic ornamental certificate."""
    S = _styles()
    teal = colors.HexColor('#0f766e')
    gold = colors.HexColor('#b7791f')
    name, _, _ = _header_lines(ctx['school'])
    el = [Spacer(1, 4),
          Paragraph(_esc(name), ParagraphStyle('sn', parent=S['center'], fontSize=12, textColor=gold,
                                               fontName='Helvetica-Bold', spaceAfter=2)),
          Paragraph('SCHOOL LEAVING CERTIFICATE', ParagraphStyle(
              'ti', parent=S['center'], fontSize=22, fontName='Times-Bold', textColor=teal, spaceAfter=8))]
    el += _cert_intro(ctx, S, colors.HexColor('#111827'))
    el.append(Paragraph(
        f"has officially completed the final year of study at {_esc(name)} and is granted this "
        f"certificate in recognition of satisfactory academic achievement and good conduct, "
        f"having attended {_career_line(ctx)}.", ParagraphStyle('p', parent=S['bodyc'], fontSize=11, leading=17)))
    el.append(Paragraph(f"Presented on {_esc(ctx.get('issued'))}.", S['bodyc']))
    el += [Spacer(1, 16), _sig_row(['Head Teacher', 'Registrar'], L_W, S, seal=True)]
    return el


def _t_modern(ctx):
    """Landscape blue + gold geometric certificate."""
    S = _styles()
    navy = colors.HexColor('#1e3a8a')
    name, _, _ = _header_lines(ctx['school'])
    el = [Spacer(1, 8),
          Paragraph('SCHOOL LEAVING<br/>CERTIFICATE', ParagraphStyle(
              'ti', parent=S['center'], fontSize=24, leading=26, fontName='Helvetica-Bold', textColor=navy, spaceAfter=8)),
          Paragraph('ISSUED TO', ParagraphStyle('it', parent=S['center'], fontSize=10,
                                                textColor=colors.HexColor('#b7791f'), spaceAfter=2)),
          Paragraph(_esc(ctx['student'].full_name), ParagraphStyle(
              'nm', parent=S['center'], fontSize=24, fontName='Times-BoldItalic', spaceAfter=4)),
          Paragraph(_esc(name), ParagraphStyle('sn', parent=S['center'], fontSize=12,
                                               fontName='Helvetica-Bold', textColor=navy, spaceAfter=8))]
    el.append(Paragraph(
        f"has officially completed the final year of study and is granted this certificate in "
        f"recognition of satisfactory academic fulfilment, having attended {_career_line(ctx)}.",
        ParagraphStyle('p', parent=S['bodyc'], fontSize=11, leading=17)))
    el.append(Paragraph(f"Dated: {_esc(ctx.get('issued'))}", S['bodyc']))
    el += [Spacer(1, 16), _sig_row(['Principal', 'Registrar'], L_W, S, seal=True)]
    return el


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
SLC_TEMPLATES = {
    'classic': {'name': 'Classic (default)', 'render': _t_classic,
                'description': 'Clean portrait certificate with a certifying paragraph and signatures.'},
    'comprehensive': {'name': 'Certificate & Testimonial', 'render': _t_comprehensive, 'decorator': _border_floral,
                      'description': 'Ornate bordered fill-in certificate & testimonial with born/from/to, subjects and character.'},
    'record': {'name': 'Leaving Record', 'render': _t_record, 'decorator': _border_gold,
               'description': 'Formal “Certificate of School Leaving” with admission/withdrawal particulars table.'},
    'awarded': {'name': 'Awarded (landscape)', 'render': _t_awarded, 'decorator': _bg_corners_blue, 'landscape': True,
                'description': 'Landscape awarded certificate with blue/gold corners, Chairman & Principal signatures + seal.'},
    'vintage': {'name': 'Vintage (landscape)', 'render': _t_vintage, 'decorator': _border_gold, 'landscape': True,
                'description': 'Landscape classic ornamental certificate with a gold double border and seal.'},
    'modern': {'name': 'Modern Geometric (landscape)', 'render': _t_modern, 'decorator': _bg_corners_blue, 'landscape': True,
               'description': 'Landscape blue & gold geometric certificate, “Issued to”, seal and signatures.'},
}
TEMPLATES = SLC_TEMPLATES
DEFAULT_TEMPLATE = 'classic'


def list_templates():
    return [{'key': k, 'name': v['name'], 'description': v['description']}
            for k, v in SLC_TEMPLATES.items()]


def resolve(key):
    return SLC_TEMPLATES.get(key) or SLC_TEMPLATES[DEFAULT_TEMPLATE]


def build_flowables(key, ctx):
    return resolve(key)['render'](ctx)


def page_decorator(key):
    return resolve(key).get('decorator')


def is_landscape(key):
    return bool(resolve(key).get('landscape'))


def sample_ctx(school):
    from utils import transcript_templates
    return transcript_templates.sample_ctx(school)
