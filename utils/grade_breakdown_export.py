"""Multi-format export (PDF, Word, Excel, HD PNG) for the Subject-Wise Grade
Breakdown report (routes.results.analytics.subject_branch_breakdown) — the
same masthead/print-safe styling as utils/broadsheet_export.py, plus the
on-screen A1-F9 / score-band colour ramp rendered as solid tints (CSS
color-mix() has no equivalent outside a browser, so these are hand-kept in
sync with the .gb-1..gb-9 rules in templates/results/subject_branch_breakdown.html).
"""
import io

from utils.broadsheet_export import _school_name, _neutral, _NEUTRAL_RGB, zip_pngs
from utils.web_exports import pdf_escape

_BAND_BASE = ['#16a34a', '#22c55e', '#4ade80', '#eab308', '#f59e0b',
             '#f97316', '#ef4444', '#dc2626', '#9333ea']
_BAND_ALPHA = [.30, .26, .22, .26, .22, .26, .20, .26, .24]
_BAND_ALPHA_HEAD = [.55, .50, .45, .50, .45, .50, .42, .50, .45]


def _blend(hex_color, alpha, base=(255, 255, 255)):
    hex_color = hex_color.lstrip('#')
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(round(c * alpha + base[i] * (1 - alpha)) for i, c in enumerate((r, g, b)))


def band_rgb(index, header=False):
    """0-based band index -> (r,g,b) print-safe tint, matching the on-screen ramp."""
    i = index % len(_BAND_BASE)
    alpha = (_BAND_ALPHA_HEAD if header else _BAND_ALPHA)[i]
    return _blend(_BAND_BASE[i], alpha)


def band_hex(index, header=False):
    r, g, b = band_rgb(index, header)
    return '#%02X%02X%02X' % (r, g, b)


def _main_headers(bands):
    return ['Subject', 'Branch', 'Candidates (N)'] + [f'{b} (%)' for b in bands]


def _summary_headers(bands, pass_label):
    return ['Branch', 'Total Subject Entries (N)'] + [f'{b} (%)' for b in bands] + [pass_label]


def _main_text_rows(result):
    bands = result['bands']
    rows = []
    for subj in result['subjects']:
        for bi, br in enumerate(result['branches']):
            cell = result['table'][subj][br]
            if cell is None:
                rows.append([subj if bi == 0 else '', br, 'Not Offered'] + [''] * len(bands))
            else:
                rows.append([subj if bi == 0 else '', br, str(cell['n'])]
                            + [f"{cell['pct'][b]}%" for b in bands])
    return rows


def _summary_text_rows(result, pass_label):
    bands = result['bands']
    rows = []
    for br in result['branches']:
        s = result['summary'][br]
        rows.append([br, str(s['n'])] + [f"{s['pct'][b]}%" for b in bands]
                    + [f"{s['pass_pct']}% ({s['pass_n']})"])
    return rows


# --------------------------------------------------------------------------- #
# PDF (reportlab, landscape A4)
# --------------------------------------------------------------------------- #

def grade_breakdown_pdf(meta, result, band_label, pass_label):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                    Spacer, Image, PageBreak, KeepTogether)
    from reportlab.lib.enums import TA_LEFT
    from reportlab.pdfbase.pdfmetrics import stringWidth

    primary, accent, light, ink = _neutral()
    head_bg = colors.HexColor('#E9EDF2')
    head_fg = colors.HexColor('#0F172A')
    rule = colors.HexColor('#94A3B8')
    grid = colors.HexColor('#D5DBE3')
    zebra = colors.HexColor('#F5F7FA')
    note_fg = colors.HexColor('#94A3B8')
    school_name = meta.get('school_name') or _school_name()
    logo_path = meta.get('logo_path')
    bands = result['bands']
    ncol = 3 + len(bands)
    fs = 10 if ncol <= 10 else (9 if ncol <= 12 else 8)

    styles = getSampleStyleSheet()
    schoolst = ParagraphStyle('sn', parent=styles['Normal'], fontSize=11, textColor=colors.HexColor('#64748B'),
                              fontName='Helvetica-Bold', alignment=TA_LEFT, spaceAfter=1)
    h = ParagraphStyle('h', parent=styles['Title'], fontSize=17, textColor=primary, spaceAfter=2, alignment=TA_LEFT)
    sub = ParagraphStyle('sub', parent=styles['Normal'], fontSize=9.5, textColor=colors.HexColor('#6B7A74'))
    cell = ParagraphStyle('c', parent=styles['Normal'], fontSize=fs, leading=fs + 2)
    cellc = ParagraphStyle('cc', parent=cell, alignment=1)
    headp = ParagraphStyle('hp', parent=styles['Normal'], fontSize=fs, leading=fs + 2,
                           textColor=head_fg, fontName='Helvetica-Bold', alignment=1)
    notep = ParagraphStyle('np', parent=cellc, textColor=note_fg, fontName='Helvetica-Oblique')

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=10 * mm, bottomMargin=12 * mm,
                            leftMargin=8 * mm, rightMargin=8 * mm, title='Grade Breakdown')
    avail = landscape(A4)[0] - 16 * mm

    def logo_flowable():
        if not logo_path:
            return None
        try:
            from PIL import Image as _PILImage
            iw, ih = _PILImage.open(logo_path).size
            lw = 20 * mm
            lh = lw * (ih / iw) if iw else 20 * mm
            return Image(logo_path, width=lw, height=min(lh, 22 * mm))
        except Exception:
            return None

    def masthead(title_text, subtitle_text):
        cells = []
        if school_name:
            cells.append(Paragraph(pdf_escape(school_name), schoolst))
        cells.append(Paragraph(pdf_escape(title_text), h))
        if subtitle_text:
            cells.append(Paragraph(pdf_escape(subtitle_text), sub))
        lg = logo_flowable()
        if lg is not None:
            mast = Table([[lg, cells]], colWidths=[24 * mm, avail - 24 * mm])
            mast.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                                      ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                      ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
            return [mast, Spacer(1, 6)]
        return list(cells) + [Spacer(1, 5)]

    def col_widths(headers, text_rows, grow_cols):
        nat = []
        for j in range(len(headers)):
            w = stringWidth(str(headers[j]), 'Helvetica-Bold', fs)
            for r in text_rows:
                if j < len(r):
                    w = max(w, stringWidth(str(r[j]), 'Helvetica', fs))
            nat.append(w + 6 * mm)
        tot = sum(nat) or 1
        widths = list(nat)
        if tot < avail:
            slack = avail - tot
            for gc in grow_cols:
                widths[gc] += slack / len(grow_cols)
        else:
            widths = [w * (avail / tot) for w in nat]
        return widths

    # ---- Main breakdown table ----
    headers = _main_headers(bands)
    widths = col_widths(headers, _main_text_rows(result), grow_cols=[0, 1])

    data = [[Paragraph(pdf_escape(x), headp) for x in headers]]
    style_cmds = [
        ('LINEBELOW', (0, 0), (-1, 0), 1.1, rule),
        ('FONTSIZE', (0, 0), (-1, -1), fs),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBELOW', (0, 1), (-1, -1), 0.4, grid),
        ('BOX', (0, 0), (-1, -1), 0.5, grid),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, grid),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('BACKGROUND', (0, 0), (2, 0), head_bg),
    ]
    for bx in range(len(bands)):
        style_cmds.append(('BACKGROUND', (3 + bx, 0), (3 + bx, 0), colors.HexColor(band_hex(bx, header=True))))

    row_i = 1
    for subj in result['subjects']:
        branches = result['branches']
        span_start = row_i
        for bi, br in enumerate(branches):
            cell_ = result['table'][subj][br]
            if cell_ is None:
                line = [Paragraph(pdf_escape(subj), cell) if bi == 0 else '',
                        Paragraph(pdf_escape(br), cell),
                        Paragraph('Not Offered', notep)] + [''] * len(bands)
                data.append(line)
                style_cmds.append(('SPAN', (2, row_i), (-1, row_i)))
            else:
                line = [Paragraph(pdf_escape(subj), cell) if bi == 0 else '',
                        Paragraph(pdf_escape(br), cell),
                        Paragraph(str(cell_['n']), cellc)]
                for bx, b in enumerate(bands):
                    line.append(Paragraph(f"{cell_['pct'][b]}%", cellc))
                    style_cmds.append(('BACKGROUND', (3 + bx, row_i), (3 + bx, row_i),
                                       colors.HexColor(band_hex(bx))))
                data.append(line)
            row_i += 1
        if len(branches) > 1:
            style_cmds.append(('SPAN', (0, span_start), (0, span_start + len(branches) - 1)))
        style_cmds.append(('LINEBELOW', (0, row_i - 1), (-1, row_i - 1), 0.8, rule))
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle(style_cmds))

    elems = [KeepTogether(masthead('Subject-Wise Performance & Grade Breakdown', meta.get('subtitle', ''))), t]

    # ---- Overall summary table (own page) ----
    sum_headers = _summary_headers(bands, pass_label)
    sum_rows = _summary_text_rows(result, pass_label)
    swidths = col_widths(sum_headers, sum_rows, grow_cols=[0])
    sdata = [[Paragraph(pdf_escape(x), headp) for x in sum_headers]]
    sstyle = [
        ('LINEBELOW', (0, 0), (-1, 0), 1.1, rule),
        ('FONTSIZE', (0, 0), (-1, -1), fs), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBELOW', (0, 1), (-1, -1), 0.4, grid),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, zebra]),
        ('BOX', (0, 0), (-1, -1), 0.5, grid), ('INNERGRID', (0, 0), (-1, -1), 0.3, grid),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('BACKGROUND', (0, 0), (1, 0), head_bg),
        ('BACKGROUND', (-1, 0), (-1, 0), head_bg),
    ]
    for bx in range(len(bands)):
        sstyle.append(('BACKGROUND', (2 + bx, 0), (2 + bx, 0), colors.HexColor(band_hex(bx, header=True))))
    for ri, br in enumerate(result['branches'], 1):
        s = result['summary'][br]
        line = [Paragraph(pdf_escape(br), cell), Paragraph(str(s['n']), cellc)]
        for bx, b in enumerate(bands):
            line.append(Paragraph(f"{s['pct'][b]}%", cellc))
            sstyle.append(('BACKGROUND', (2 + bx, ri), (2 + bx, ri), colors.HexColor(band_hex(bx))))
        line.append(Paragraph(f"<b>{s['pass_pct']}%</b> ({s['pass_n']})", cellc))
        sdata.append(line)
    st = Table(sdata, colWidths=swidths, repeatRows=1)
    st.setStyle(TableStyle(sstyle))

    elems.append(PageBreak())
    elems.append(KeepTogether(masthead(f'Overall {band_label} Percentage Summary by Branch', '')))
    elems.append(st)

    doc.build(elems)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Word (.docx)
# --------------------------------------------------------------------------- #

def grade_breakdown_docx(meta, result, band_label, pass_label):
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import nsdecls
    from docx.oxml import parse_xml
    from docx.enum.section import WD_ORIENT
    import os as _os

    school_name = meta.get('school_name') or _school_name()
    logo_path = meta.get('logo_path')
    navy = RGBColor(0x33, 0x41, 0x55)
    muted = RGBColor(0x64, 0x74, 0x8B)
    note_rgb = RGBColor(0x94, 0xA3, 0xB8)
    bands = result['bands']
    ncol = 3 + len(bands)
    fs = 10 if ncol <= 10 else (9 if ncol <= 12 else 8)

    doc = Document()
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = sec.page_height, sec.page_width
    sec.left_margin = sec.right_margin = Cm(1.0)
    sec.top_margin = sec.bottom_margin = Cm(1.0)

    def shade(cell, hexcolor):
        cell._tc.get_or_add_tcPr().append(parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hexcolor.lstrip("#")}"/>'))

    def masthead(title_text, subtitle_text):
        if logo_path and _os.path.exists(logo_path):
            try:
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                p.add_run().add_picture(logo_path, height=Cm(1.4))
            except Exception:
                pass
        if school_name:
            sp = doc.add_paragraph()
            r = sp.add_run(school_name)
            r.bold = True; r.font.size = Pt(11); r.font.color.rgb = muted
        hp = doc.add_paragraph()
        hr = hp.add_run(title_text)
        hr.bold = True; hr.font.size = Pt(16); hr.font.color.rgb = navy
        if subtitle_text:
            sb = doc.add_paragraph()
            sr = sb.add_run(subtitle_text)
            sr.font.size = Pt(9); sr.font.color.rgb = muted

    def set_cell(cell, text, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER, size=fs, italic=False, color=None):
        cell.text = str(text)
        pr = cell.paragraphs[0]
        pr.alignment = align
        if pr.runs:
            run = pr.runs[0]
            run.bold = bold; run.italic = italic; run.font.size = Pt(size)
            if color is not None:
                run.font.color.rgb = color

    masthead('Subject-Wise Performance & Grade Breakdown', meta.get('subtitle', ''))

    headers = _main_headers(bands)
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = 'Table Grid'
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, label in enumerate(headers):
        set_cell(t.rows[0].cells[i], label, bold=True)
        shade(t.rows[0].cells[i], band_hex(i - 3, header=True) if i >= 3 else '#E9EDF2')

    for subj in result['subjects']:
        branches = result['branches']
        first_row_idx = None
        for bi, br in enumerate(branches):
            row = t.add_row()
            cells = row.cells
            if first_row_idx is None:
                first_row_idx = len(t.rows) - 1
            cell_ = result['table'][subj][br]
            set_cell(cells[1], br, align=WD_ALIGN_PARAGRAPH.LEFT)
            if cell_ is None:
                merged = cells[2]
                for k in range(3, len(headers)):
                    merged = merged.merge(cells[k])
                set_cell(merged, 'Not Offered', italic=True, color=note_rgb)
            else:
                set_cell(cells[2], cell_['n'])
                for bx, b in enumerate(bands):
                    set_cell(cells[3 + bx], f"{cell_['pct'][b]}%")
                    shade(cells[3 + bx], band_hex(bx))
            if bi == 0:
                set_cell(cells[0], subj, bold=True, align=WD_ALIGN_PARAGRAPH.LEFT)
        if len(branches) > 1:
            top = t.rows[first_row_idx].cells[0]
            for k in range(1, len(branches)):
                top = top.merge(t.rows[first_row_idx + k].cells[0])
            top.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT

    doc.add_page_break()
    masthead(f'Overall {band_label} Percentage Summary by Branch', '')
    sum_headers = _summary_headers(bands, pass_label)
    st = doc.add_table(rows=1, cols=len(sum_headers))
    st.style = 'Table Grid'
    st.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, label in enumerate(sum_headers):
        set_cell(st.rows[0].cells[i], label, bold=True)
        shade(st.rows[0].cells[i], band_hex(i - 2, header=True) if 2 <= i < 2 + len(bands) else '#E9EDF2')
    for br in result['branches']:
        s = result['summary'][br]
        row = st.add_row()
        cells = row.cells
        set_cell(cells[0], br, align=WD_ALIGN_PARAGRAPH.LEFT)
        set_cell(cells[1], s['n'])
        for bx, b in enumerate(bands):
            set_cell(cells[2 + bx], f"{s['pct'][b]}%")
            shade(cells[2 + bx], band_hex(bx))
        set_cell(cells[-1], f"{s['pass_pct']}% ({s['pass_n']})", bold=True)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Excel (.xlsx)
# --------------------------------------------------------------------------- #

def grade_breakdown_xlsx(meta, result, band_label, pass_label):
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = 'Grade Breakdown'
    hf = Font(bold=True, color='0F172A')
    head_fill = PatternFill('solid', fgColor='E9EDF2')
    ctr = Alignment(horizontal='center', vertical='center')
    left = Alignment(horizontal='left', vertical='center')
    school_name = meta.get('school_name') or _school_name()
    bands = result['bands']

    r = 1
    if school_name:
        ws.cell(row=r, column=1, value=school_name).font = Font(bold=True, color='64748B')
        r += 1
    ws.cell(row=r, column=1, value='Subject-Wise Performance & Grade Breakdown').font = \
        Font(bold=True, size=14, color='334155')
    r += 1
    if meta.get('subtitle'):
        ws.cell(row=r, column=1, value=meta['subtitle']).font = Font(color='6B7A74')
        r += 1
    r += 1

    headers = _main_headers(bands)
    hrow = r
    for c, label in enumerate(headers, 1):
        cell = ws.cell(row=hrow, column=c, value=label)
        cell.font = hf; cell.alignment = ctr
        cell.fill = PatternFill('solid', fgColor=band_hex(c - 4, header=True).lstrip('#')) if c >= 4 else head_fill
    r += 1
    data_start = r
    for subj in result['subjects']:
        branches = result['branches']
        subj_start = r
        for br in branches:
            cell_ = result['table'][subj][br]
            ws.cell(row=r, column=2, value=br).alignment = left
            if cell_ is None:
                nc = ws.cell(row=r, column=3, value='Not Offered')
                nc.alignment = ctr
                nc.font = Font(italic=True, color='94A3B8')
                ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=3 + len(bands))
            else:
                ws.cell(row=r, column=3, value=cell_['n']).alignment = ctr
                for bx, b in enumerate(bands):
                    c_ = ws.cell(row=r, column=4 + bx, value=cell_['pct'][b] / 100)
                    c_.number_format = '0.0%'
                    c_.alignment = ctr
                    c_.fill = PatternFill('solid', fgColor=band_hex(bx).lstrip('#'))
            r += 1
        subj_cell = ws.cell(row=subj_start, column=1, value=subj)
        subj_cell.alignment = left
        subj_cell.font = Font(bold=True)
        if len(branches) > 1:
            ws.merge_cells(start_row=subj_start, start_column=1, end_row=r - 1, end_column=1)
    ws.freeze_panes = ws.cell(row=data_start, column=1)
    for c in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(c)].width = 22 if c <= 2 else 14

    ws2 = wb.create_sheet('Summary')
    r2 = 1
    ws2.cell(row=r2, column=1, value=f'Overall {band_label} Percentage Summary by Branch').font = \
        Font(bold=True, size=13, color='334155')
    r2 += 2
    sum_headers = _summary_headers(bands, pass_label)
    for c, label in enumerate(sum_headers, 1):
        cell = ws2.cell(row=r2, column=c, value=label)
        cell.font = hf; cell.alignment = ctr
        cell.fill = (PatternFill('solid', fgColor=band_hex(c - 3, header=True).lstrip('#'))
                     if 3 <= c < 3 + len(bands) else head_fill)
    r2 += 1
    for br in result['branches']:
        s = result['summary'][br]
        ws2.cell(row=r2, column=1, value=br).alignment = left
        ws2.cell(row=r2, column=2, value=s['n']).alignment = ctr
        for bx, b in enumerate(bands):
            c_ = ws2.cell(row=r2, column=3 + bx, value=s['pct'][b] / 100)
            c_.number_format = '0.0%'
            c_.alignment = ctr
            c_.fill = PatternFill('solid', fgColor=band_hex(bx).lstrip('#'))
        last = ws2.cell(row=r2, column=3 + len(bands), value=f"{s['pass_pct']}% ({s['pass_n']})")
        last.alignment = ctr
        last.font = Font(bold=True)
        r2 += 1
    for c in range(1, len(sum_headers) + 1):
        ws2.column_dimensions[get_column_letter(c)].width = 20 if c == 1 else 16
    return wb


# --------------------------------------------------------------------------- #
# HD PNG (Pillow, landscape A4 @ 200dpi) — bundled into a zip when >1 page
# --------------------------------------------------------------------------- #

def grade_breakdown_png_pages(meta, result, band_label, pass_label):
    from PIL import Image, ImageDraw, ImageFont
    S = 2
    DPI = 200
    PW = int(round(297 / 25.4 * DPI))
    PH = int(round(210 / 25.4 * DPI))
    C = _NEUTRAL_RGB
    school_name = meta.get('school_name') or _school_name()
    logo_path = meta.get('logo_path')
    bands = result['bands']
    ncol = 3 + len(bands)

    def fnt(size, bold=False):
        path = "/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if bold else "")
        try:
            return ImageFont.truetype(path, int(size * S))
        except Exception:
            return ImageFont.load_default()

    fs = 22 if ncol <= 10 else (18 if ncol <= 12 else 15)
    body, body_b = fnt(fs), fnt(fs, True)
    title_f, sub_f, key_f = fnt(26, True), fnt(14), fnt(13)
    tmp = ImageDraw.Draw(Image.new('RGB', (1, 1)))

    def tw(text, f):
        b = tmp.textbbox((0, 0), str(text), font=f)
        return b[2] - b[0]

    def fit(text, f, maxw):
        text = str(text)
        if tw(text, f) <= maxw:
            return text
        while text and tw(text + '…', f) > maxw:
            text = text[:-1]
        return (text + '…') if text else ''

    margin = 34 * S
    avail = PW * S - 2 * margin
    cpx, cpy = int(9 * S), int(7 * S)

    logo_im = None
    if logo_path:
        try:
            logo_im = Image.open(logo_path).convert('RGBA')
        except Exception:
            logo_im = None
    logo_box = int(64 * S)
    logo_draw = None
    if logo_im is not None:
        lw, lh = logo_im.size
        scale = logo_box / max(lw, lh)
        logo_draw = logo_im.resize((max(1, int(lw * scale)), max(1, int(lh * scale))), Image.LANCZOS)
    text_x = margin + (logo_box + int(14 * S) if logo_draw is not None else 0)

    def draw_masthead(d, img, title_text, subtitle_text):
        if logo_draw is not None:
            img.paste(logo_draw, (margin, margin), logo_draw)
        ty = margin
        text_avail = PW * S - margin - text_x
        if school_name:
            d.text((text_x, ty), fit(school_name, sub_f, text_avail), fill=C['muted'], font=sub_f)
            ty += int(20 * S)
        d.text((text_x, ty), fit(title_text, title_f, text_avail), fill=C['header'], font=title_f)
        ty += int(34 * S)
        if subtitle_text:
            d.text((text_x, ty), fit(subtitle_text, sub_f, text_avail), fill=C['muted'], font=sub_f)
        mast_lines = int(34 * S) + (int(20 * S) if school_name else 0) + (int(22 * S) if subtitle_text else 0)
        return max(mast_lines, logo_box if logo_draw is not None else 0)

    def measure(headers, text_rows, grow_cols):
        nat = []
        for j in range(len(headers)):
            w = tw(headers[j], body_b)
            for r in text_rows:
                w = max(w, tw(r[j] if j < len(r) else '', body))
            nat.append(w + 2 * cpx)
        tot = sum(nat) or 1
        widths = list(nat)
        if tot < avail:
            slack = avail - tot
            for gc in grow_cols:
                widths[gc] += slack / len(grow_cols)
        else:
            widths = [w * (avail / tot) for w in nat]
        return [int(w) for w in widths]

    line_h = tmp.textbbox((0, 0), "Ay", font=body)[3]
    row_h = line_h + 2 * cpy
    header_h = row_h + int(4 * S)
    bottom_reserve = margin + int(24 * S)
    top_gap = int(12 * S)

    pages = []

    def new_page(title_text, subtitle_text, draw_mast):
        img = Image.new('RGB', (PW * S, PH * S), C['white'])
        d = ImageDraw.Draw(img)
        if draw_mast:
            mh = draw_masthead(d, img, title_text, subtitle_text)
            y0 = margin + mh
        else:
            y0 = margin + top_gap
        return img, d, y0

    def save_page(img):
        out = io.BytesIO()
        img.resize((PW, PH), Image.LANCZOS).save(out, format='PNG')
        pages.append(out.getvalue())

    # ---- Main breakdown table (paginates whole subject-blocks) ----
    headers = _main_headers(bands)
    col_w = measure(headers, _main_text_rows(result), grow_cols=[0, 1])
    table_w = sum(col_w)
    page_title = 'Subject-Wise Performance & Grade Breakdown'
    subtitle_text = meta.get('subtitle', '')

    def draw_header_row(d, y0):
        d.rectangle([margin, y0, margin + table_w, y0 + header_h], fill=C['head_bg'])
        x = margin
        for j in range(len(headers)):
            if j >= 3:
                d.rectangle([x, y0, x + col_w[j], y0 + header_h], fill=band_rgb(j - 3, header=True))
            d.text((x + cpx, y0 + (header_h - line_h) // 2), fit(headers[j], body_b, col_w[j] - 2 * cpx),
                   fill=C['head_fg'], font=body_b)
            x += col_w[j]
        d.rectangle([margin, y0 + header_h - max(2, S), margin + table_w, y0 + header_h], fill=C['rule'])
        return y0 + header_h

    def grid_lines(d, y0, y):
        d.rectangle([margin, y0, margin + table_w, y], outline=C['line'], width=1)
        x = margin
        for j in range(len(headers) - 1):
            x += col_w[j]
            d.line([x, y0, x, y], fill=C['line'], width=1)

    img, d, y0 = new_page(page_title, subtitle_text, draw_mast=True)
    y = draw_header_row(d, y0)
    max_y = PH * S - bottom_reserve

    for subj in result['subjects']:
        branches = result['branches']
        need_h = row_h * len(branches)
        if y + need_h > max_y and y > y0 + header_h:
            grid_lines(d, y0, y)
            save_page(img)
            img, d, y0 = new_page(page_title, subtitle_text, draw_mast=False)
            y = draw_header_row(d, y0)
        subj_top = y
        for ri, br in enumerate(branches):
            cell_ = result['table'][subj][br]
            if ri % 2:
                d.rectangle([margin, y, margin + table_w, y + row_h], fill=C['zebra'])
            x = margin + col_w[0]
            d.text((x + cpx, y + cpy), fit(br, body, col_w[1] - 2 * cpx), fill=C['text'], font=body)
            x += col_w[1]
            if cell_ is None:
                rest_w = sum(col_w[2:])
                txt = 'Not Offered'
                tx = x + (rest_w - tw(txt, body)) / 2
                d.text((tx, y + cpy), txt, fill=C['muted'], font=body)
            else:
                ntxt = str(cell_['n'])
                d.text((x + (col_w[2] - tw(ntxt, body)) / 2, y + cpy), ntxt, fill=C['text'], font=body)
                x += col_w[2]
                for bx, b in enumerate(bands):
                    bw = col_w[3 + bx]
                    d.rectangle([x, y, x + bw, y + row_h], fill=band_rgb(bx))
                    txt = f"{cell_['pct'][b]}%"
                    tx = x + (bw - tw(txt, body)) / 2
                    d.text((tx, y + cpy), txt, fill=C['text'], font=body)
                    x += bw
            d.line([margin, y, margin + table_w, y], fill=C['line'], width=1)
            y += row_h
        d.text((margin + cpx, subj_top + max(0, (y - subj_top - line_h) / 2)),
               fit(subj, body_b, col_w[0] - 2 * cpx), fill=C['text'], font=body_b)
        d.line([margin, y, margin + table_w, y], fill=C['rule'], width=2)

    grid_lines(d, y0, y)
    save_page(img)

    # ---- Overall summary (own page) ----
    sum_headers = _summary_headers(bands, pass_label)
    sum_rows = _summary_text_rows(result, pass_label)
    scol_w = measure(sum_headers, sum_rows, grow_cols=[0])
    stable_w = sum(scol_w)
    simg, sd, sy0 = new_page(f'Overall {band_label} Percentage Summary by Branch', '', draw_mast=True)
    sd.rectangle([margin, sy0, margin + stable_w, sy0 + header_h], fill=C['head_bg'])
    x = margin
    for j, label in enumerate(sum_headers):
        if 2 <= j < 2 + len(bands):
            sd.rectangle([x, sy0, x + scol_w[j], sy0 + header_h], fill=band_rgb(j - 2, header=True))
        sd.text((x + cpx, sy0 + (header_h - line_h) // 2), fit(label, body_b, scol_w[j] - 2 * cpx),
                fill=C['head_fg'], font=body_b)
        x += scol_w[j]
    sd.rectangle([margin, sy0 + header_h - max(2, S), margin + stable_w, sy0 + header_h], fill=C['rule'])
    sy = sy0 + header_h
    for i, br in enumerate(result['branches']):
        s = result['summary'][br]
        if i % 2:
            sd.rectangle([margin, sy, margin + stable_w, sy + row_h], fill=C['zebra'])
        x = margin
        sd.text((x + cpx, sy + cpy), fit(br, body, scol_w[0] - 2 * cpx), fill=C['text'], font=body)
        x += scol_w[0]
        ntxt = str(s['n'])
        sd.text((x + (scol_w[1] - tw(ntxt, body)) / 2, sy + cpy), ntxt, fill=C['text'], font=body)
        x += scol_w[1]
        for bx, b in enumerate(bands):
            bw = scol_w[2 + bx]
            sd.rectangle([x, sy, x + bw, sy + row_h], fill=band_rgb(bx))
            txt = f"{s['pct'][b]}%"
            tx = x + (bw - tw(txt, body)) / 2
            sd.text((tx, sy + cpy), txt, fill=C['text'], font=body)
            x += bw
        last = f"{s['pass_pct']}% ({s['pass_n']})"
        sd.text((x + (scol_w[-1] - tw(last, body_b)) / 2, sy + cpy), last, fill=C['text'], font=body_b)
        sd.line([margin, sy, margin + stable_w, sy], fill=C['line'], width=1)
        sy += row_h
    sd.rectangle([margin, sy0, margin + stable_w, sy], outline=C['line'], width=1)
    x = margin
    for j in range(len(sum_headers) - 1):
        x += scol_w[j]
        sd.line([x, sy0, x, sy], fill=C['line'], width=1)
    save_page(simg)

    return pages


def grade_breakdown_image_export(meta, result, band_label, pass_label):
    """Returns (bytes, mimetype, ext) — a single HD PNG, or a zip of pages."""
    pages = grade_breakdown_png_pages(meta, result, band_label, pass_label)
    if len(pages) == 1:
        return pages[0], 'image/png', 'png'
    return zip_pngs(pages, base='grade_breakdown'), 'application/zip', 'zip'
