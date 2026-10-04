"""PDF, Excel and HD-image exports for a Study Groups set. The image export
(``build_png``) is drawn server-side with Pillow -- a branded masthead plus a
grid of navy-headed group cards -- using the same visual language as
``utils/student_export.py``; it is not a screenshot of the rendered page."""
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


def build_png(data, school):
    """A branded HD PNG of the board: masthead (logo, school identity, an info
    panel) above a grid of navy-headed group cards, one row per member with
    the leader picked out by a gold tint -- same design language as
    ``utils/student_export.py``'s image export, drawn from scratch with
    Pillow rather than captured from the page."""
    import os
    from PIL import Image, ImageDraw, ImageFont
    from utils.student_export import _FONT_REG, _FONT_BOLD, _FONT_ITAL
    from utils.numfmt import fmt_num as n
    from utils import timeutil

    NAVY, GOLD, INK, MUTED = (30, 42, 74), (184, 134, 43), (31, 41, 55), (107, 114, 128)
    LINE, WHITE, PANEL, ZEBRA = (216, 222, 233), (255, 255, 255), (247, 248, 250), (248, 250, 252)
    LEADER_BG, LEADER_BORDER = (255, 247, 224), (244, 208, 111)

    S = 2                       # supersample factor; downscaled at the end for anti-aliasing
    BASE_W = 1500
    W = BASE_W * S
    margin = 36 * S

    def fnt(size, bold=False, italic=False):
        p = _FONT_BOLD if bold else (_FONT_ITAL if italic else _FONT_REG)
        try:
            return ImageFont.truetype(p, int(size * S))
        except Exception:
            return ImageFont.load_default()

    probe = ImageDraw.Draw(Image.new('RGB', (1, 1)))

    def tw(t, f):
        b = probe.textbbox((0, 0), str(t), font=f)
        return b[2] - b[0]

    def th(f):
        b = probe.textbbox((0, 0), 'Ay', font=f)
        return b[3] - b[1]

    def fit(t, f, mw):
        t = str(t)
        if tw(t, f) <= mw:
            return t
        while t and tw(t + '…', f) > mw:
            t = t[:-1]
        return (t + '…') if t else ''

    name_f = fnt(28, True)
    addr_f = fnt(13)
    motto_f = fnt(13, italic=True)
    panel_lab, panel_val = fnt(10), fnt(17, True)
    title_f = fnt(24, True)
    meta_f = fnt(12)
    hdr_f, count_f = fnt(14, True), fnt(11)
    member_f, member_b, avg_f = fnt(13), fnt(13, True), fnt(11)
    foot_b, foot_s = fnt(10, True), fnt(9)

    groups = data.get('groups') or []
    title = data.get('title') or 'Study Groups'
    basis_term_name = data.get('basis_term_name')
    meta_line = (f"{data.get('class_name', '')}  ·  {data.get('term_name', '')}  ·  "
                f"{data.get('num_groups')} group(s) of {data.get('group_size')}  ·  " +
                (f"ranked by {basis_term_name} average" if basis_term_name
                 else 'no prior-term data available — placed randomly'))
    sub_line = f"by {data.get('created_by', '')} on {data.get('created_at', '')}"

    # ---- masthead ----
    mast_h = 150 * S
    title_h = int(th(title_f) * 1.9)
    meta_h = int(th(meta_f) * 1.6) * 2

    # ---- grid layout ----
    gap = 18 * S
    min_card_w = 320 * S
    avail = W - 2 * margin
    cols = max(1, min(4, int((avail + gap) // (min_card_w + gap))))
    card_w = int((avail - (cols - 1) * gap) / cols)

    row_h_hdr = 40 * S
    member_row_h = int(th(member_f) * 2.0)
    pad_x = 14 * S

    def card_height(g):
        return row_h_hdr + max(1, len(g.get('members') or [])) * member_row_h

    rows_layout = [groups[i:i + cols] for i in range(0, len(groups), cols)] or [[]]
    body_top = margin + mast_h + title_h + meta_h + 10 * S
    y = body_top
    row_tops = []
    for chunk in rows_layout:
        h = max((card_height(g) for g in chunk), default=0)
        row_tops.append((y, h))
        y += h + gap
    body_bottom = (y - gap) if groups else body_top
    foot_h = 44 * S
    H = int(body_bottom + foot_h + margin)

    img = Image.new('RGB', (W, H), WHITE)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([int(margin * 0.55), int(margin * 0.55), W - int(margin * 0.55), H - int(margin * 0.55)],
                        radius=16, outline=GOLD, width=3)

    # ---- masthead: logo + school identity (left), info panel (right) ----
    x = margin + 10 * S
    logo = (school or {}).get('logo_path')
    lx = x
    if logo and os.path.exists(logo):
        try:
            lg = Image.open(logo).convert('RGBA')
            h = 130 * S
            w = int(lg.width * h / lg.height)
            lg = lg.resize((min(w, int(150 * S)), h), Image.LANCZOS)
            img.paste(lg, (x, margin + 10 * S), lg)
            lx = x + min(w, int(150 * S)) + 24 * S
        except Exception:
            lx = x

    pw, ph = 500 * S, 126 * S
    px, py = W - margin - 10 * S - pw, margin + 10 * S
    right_limit = px - 24 * S
    d.rounded_rectangle([px, py, px + pw, py + ph], radius=12 * S, fill=PANEL, outline=LINE, width=2)
    cells = [('GROUPS', str(data.get('num_groups') or len(groups))),
             ('PER GROUP', str(data.get('group_size') or '')),
             ('DATE', timeutil.today().strftime('%d %b %Y'))]
    cwid = pw / 3
    for i, (lab, val) in enumerate(cells):
        cx = px + i * cwid + cwid / 2
        d.text((cx - tw(lab, panel_lab) / 2, py + 22 * S), lab, fill=MUTED, font=panel_lab)
        d.text((cx - tw(val, panel_val) / 2, py + 64 * S), val, fill=NAVY, font=panel_val)
        if i:
            d.line([px + i * cwid, py + 18 * S, px + i * cwid, py + ph - 18 * S], fill=LINE, width=1)

    nm = ((school or {}).get('name') or 'School').upper()
    nf, nsz = name_f, 28
    while nsz > 16 and tw(nm, nf) > (right_limit - lx):
        nsz -= 2
        nf = fnt(nsz, True)
    name_top = margin + 14 * S
    d.text((lx, name_top), fit(nm, nf, right_limit - lx), fill=NAVY, font=nf)
    ty = name_top + th(nf) + 16 * S
    addr = (school or {}).get('address') or ''
    if addr:
        d.text((lx, ty), fit('●  ' + addr, addr_f, right_limit - lx), fill=INK, font=addr_f)
        ty += th(addr_f) + 14 * S
    contact = '      '.join(p for p in [(school or {}).get('phone') or '', (school or {}).get('email') or ''] if p)
    if contact:
        d.text((lx, ty), fit(contact, addr_f, right_limit - lx), fill=INK, font=addr_f)
        ty += th(addr_f) + 14 * S
    motto = (school or {}).get('motto') or ''
    if motto:
        d.text((lx, ty), fit('—  ' + motto + '  —', motto_f, right_limit - lx), fill=GOLD, font=motto_f)

    # ---- title + meta ----
    ty0 = margin + mast_h
    tt = fit(str(title), title_f, W - 2 * margin)
    d.text((W / 2 - tw(tt, title_f) / 2, ty0 + (title_h - th(title_f)) / 2), tt, fill=NAVY, font=title_f)
    mt = fit(meta_line, meta_f, W - 2 * margin)
    d.text((W / 2 - tw(mt, meta_f) / 2, ty0 + title_h), mt, fill=MUTED, font=meta_f)
    st = fit(sub_line, meta_f, W - 2 * margin)
    d.text((W / 2 - tw(st, meta_f) / 2, ty0 + title_h + th(meta_f) * 1.6), st, fill=MUTED, font=meta_f)

    # ---- group cards ----
    gi = 0
    for row_i, chunk in enumerate(rows_layout):
        row_y, row_h = row_tops[row_i] if groups else (body_top, 0)
        for col_i, g in enumerate(chunk):
            cx0 = margin + col_i * (card_w + gap)
            ch = card_height(g)
            d.rectangle([cx0, row_y, cx0 + card_w, row_y + ch], outline=LINE, width=2)
            d.rectangle([cx0, row_y, cx0 + card_w, row_y + row_h_hdr], fill=NAVY)
            d.rectangle([cx0, row_y + row_h_hdr - 3 * S, cx0 + card_w, row_y + row_h_hdr], fill=GOLD)
            members = g.get('members') or []
            label = f"{g.get('label', '')}  ·  {len(members)}"
            d.text((cx0 + pad_x, row_y + (row_h_hdr - th(hdr_f)) / 2), fit(label, hdr_f, card_w - 2 * pad_x),
                   fill=WHITE, font=hdr_f)
            yy = row_y + row_h_hdr
            if not members:
                d.text((cx0 + pad_x, yy + 10 * S), 'No members', fill=MUTED, font=member_f)
            for idx, m in enumerate(members):
                is_leader = bool(m.get('is_leader'))
                bg = LEADER_BG if is_leader else (ZEBRA if idx % 2 else WHITE)
                d.rectangle([cx0 + 2, yy, cx0 + card_w - 2, yy + member_row_h], fill=bg)
                if is_leader:
                    d.rectangle([cx0 + 2, yy, cx0 + 5 * S, yy + member_row_h], fill=GOLD)
                avg = m.get('basis_average')
                avg_txt = n(avg) if avg is not None else ''
                avg_w = tw(avg_txt, avg_f) if avg_txt else 0
                name_mw = card_w - 2 * pad_x - avg_w - (8 * S if avg_w else 0)
                name_font = member_b if is_leader else member_f
                name_txt = fit(m.get('name', ''), name_font, name_mw)
                tyy = yy + (member_row_h - th(name_font)) / 2
                d.text((cx0 + pad_x, tyy), name_txt, fill=(NAVY if is_leader else INK), font=name_font)
                if avg_txt:
                    d.text((cx0 + card_w - pad_x - avg_w, yy + (member_row_h - th(avg_f)) / 2), avg_txt,
                           fill=MUTED, font=avg_f)
                d.line([cx0 + 2, yy + member_row_h, cx0 + card_w - 2, yy + member_row_h], fill=LINE, width=1)
                yy += member_row_h
            gi += 1

    # ---- footer ----
    fy = H - margin - foot_h + 10 * S
    d.line([margin, fy, W - margin, fy], fill=LINE, width=1)
    school_name = ((school or {}).get('name') or 'School').upper()
    d.text((margin, fy + 10 * S), school_name, fill=NAVY, font=foot_b)
    conf = 'This document is system-generated and confidential.'
    d.text((W - margin - tw(conf, foot_s), fy + 10 * S), conf, fill=MUTED, font=foot_s)

    out_w, out_h = BASE_W, max(1, H // S)
    buf = io.BytesIO()
    img.resize((out_w, out_h), Image.LANCZOS).save(buf, format='PNG')
    buf.seek(0)
    return buf
