"""Multi-format export (PDF, Word, Excel, HD PNG) for the Subject-Wise Grade
Breakdown report (routes.results.analytics.subject_branch_breakdown) —
a navy masthead + two-tier colour-coded header, matching the school's own
printed grade-analysis-sheet template. The on-screen A1-F9 / score-band
colour ramp (CSS color-mix(), no equivalent outside a browser) is hand-kept
in sync with the .gb-1..gb-9 rules in templates/results/subject_branch_breakdown.html:
header cells use the base hue at full strength, body cells a light tint.
"""
import io

from utils.broadsheet_export import _school_name, _NEUTRAL_RGB, zip_pngs
from utils.web_exports import pdf_escape

NAVY_HEX = '#173A63'
NAVY_RGB = (23, 58, 99)

_BAND_BASE = ['#16a34a', '#22c55e', '#4ade80', '#eab308', '#f59e0b',
             '#f97316', '#ef4444', '#dc2626', '#9333ea']
_BAND_ALPHA = [.30, .26, .22, .26, .22, .26, .20, .26, .24]


def _blend(hex_color, alpha, base=(255, 255, 255)):
    hex_color = hex_color.lstrip('#')
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(round(c * alpha + base[i] * (1 - alpha)) for i, c in enumerate((r, g, b)))


def band_rgb(index, header=False):
    """0-based band index -> (r,g,b). ``header=True`` is the vivid, near-full-
    strength swatch used on the colour-coded header cells; the default is the
    light print-safe tint used on the data cells beneath it."""
    i = index % len(_BAND_BASE)
    if header:
        hexc = _BAND_BASE[i].lstrip('#')
        return tuple(int(hexc[j:j + 2], 16) for j in (0, 2, 4))
    return _blend(_BAND_BASE[i], _BAND_ALPHA[i])


def band_hex(index, header=False):
    r, g, b = band_rgb(index, header)
    return '#%02X%02X%02X' % (r, g, b)


def _text_on(rgb):
    """Black or white — whichever reads better on this background."""
    r, g, b = rgb
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return (255, 255, 255) if luminance < 0.62 else (15, 23, 42)


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


def _docx_col_widths(name_lens, name_headers, name_caps, extra_header, avail_cm, n_band_cols, tail_label=None):
    """Column widths (cm) for a docx table: name-ish columns sized to their
    content (capped), band columns splitting whatever's left evenly — never
    letting Subject/Branch balloon out to fill the page like Word's default
    equal-split would."""
    from docx.shared import Cm
    widths = []
    for lens, header, cap in zip(name_lens, name_headers, name_caps):
        w = min(max(max(lens, default=8), len(header)) * 0.22 + 0.6, cap)
        widths.append(w)
    n_cm = len(extra_header) * 0.16 + 0.5
    widths.append(n_cm)
    tail_cm = min(len(tail_label) * 0.16 + 0.6, 5.5) if tail_label else 0
    band_cm = (avail_cm - sum(widths) - tail_cm) / n_band_cols
    widths += [band_cm] * n_band_cols
    if tail_label:
        widths.append(tail_cm)
    return [Cm(w) for w in widths]


def _apply_docx_col_widths(table, widths):
    table.autofit = False
    for i, w in enumerate(widths):
        table.columns[i].width = w
    for row in table.rows:
        for i, cell in enumerate(row.cells):
            if i < len(widths):
                cell.width = widths[i]


# --------------------------------------------------------------------------- #
# PDF (reportlab, landscape A4)
# --------------------------------------------------------------------------- #

def grade_breakdown_pdf(meta, result, band_label, pass_label):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                    Spacer, KeepTogether)
    from reportlab.pdfbase.pdfmetrics import stringWidth

    grid = colors.HexColor('#B9C2CE')
    note_fg = colors.HexColor('#94A3B8')
    navy = colors.HexColor(NAVY_HEX)
    school_name = (meta.get('school_name') or _school_name() or '').strip()
    bands = result['bands']
    ncol = 3 + len(bands)
    fs = 10 if ncol <= 10 else (9 if ncol <= 12 else 8)

    def rl_color(rgb):
        return colors.Color(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)

    styles = getSampleStyleSheet()
    banner_l = ParagraphStyle('bl', parent=styles['Normal'], fontSize=15, leading=18,
                              textColor=colors.white, fontName='Helvetica-Bold', alignment=1)
    banner_s = ParagraphStyle('bs', parent=styles['Normal'], fontSize=11.5, leading=14,
                              textColor=colors.white, fontName='Helvetica-Bold', alignment=1)
    cell = ParagraphStyle('c', parent=styles['Normal'], fontSize=fs, leading=fs + 2)
    cellc = ParagraphStyle('cc', parent=cell, alignment=1)
    notep = ParagraphStyle('np', parent=cellc, textColor=note_fg, fontName='Helvetica-Oblique')
    legendp = ParagraphStyle('lg', parent=styles['Normal'], fontSize=8, textColor=note_fg,
                             fontName='Helvetica-Oblique')

    def headp_for(rgb):
        fg = _text_on(rgb)
        return ParagraphStyle('hp%d' % id(rgb), parent=styles['Normal'], fontSize=fs, leading=fs + 2,
                              textColor=rl_color(fg), fontName='Helvetica-Bold', alignment=1)
    navy_headp = headp_for(NAVY_RGB)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=8 * mm, bottomMargin=10 * mm,
                            leftMargin=8 * mm, rightMargin=8 * mm, title='Grade Breakdown')
    avail = landscape(A4)[0] - 16 * mm

    def banner(title_text):
        rows = []
        if school_name:
            rows.append([Paragraph(pdf_escape(school_name.upper()), banner_l)])
        rows.append([Paragraph(pdf_escape(title_text.upper()), banner_s)])
        bt = Table(rows, colWidths=[avail])
        bt.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), navy), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        return [bt, Spacer(1, 8)]

    def sub_banner(title_text):
        # A slim single-line navy bar (no school name repeat) — the summary
        # table sits right under the main one on the same page, not its own.
        bt = Table([[Paragraph(pdf_escape(title_text.upper()), banner_s)]], colWidths=[avail])
        bt.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), navy), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        return [bt, Spacer(1, 6)]

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
    widths = col_widths(headers, _main_text_rows(result), grow_cols=list(range(3, 3 + len(bands))))
    span_label = f'{band_label} Percentage Breakdown'.upper()

    row0 = [Paragraph('SUBJECT', navy_headp), Paragraph('BRANCH', navy_headp),
           Paragraph('CANDIDATES (N)', navy_headp), Paragraph(pdf_escape(span_label), navy_headp)] \
        + [''] * (len(bands) - 1)
    row1 = ['', '', ''] + [Paragraph(f'{b} (%)', headp_for(band_rgb(i, header=True)))
                           for i, b in enumerate(bands)]
    data = [row0, row1]
    style_cmds = [
        ('SPAN', (0, 0), (0, 1)), ('SPAN', (1, 0), (1, 1)), ('SPAN', (2, 0), (2, 1)),
        ('SPAN', (3, 0), (3 + len(bands) - 1, 0)),
        ('BACKGROUND', (0, 0), (2, 1), navy), ('BACKGROUND', (3, 0), (-1, 0), navy),
        ('FONTSIZE', (0, 0), (-1, -1), fs), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBELOW', (0, 1), (-1, 1), 1.1, navy),
        ('LINEBELOW', (0, 2), (-1, -1), 0.4, grid),
        ('BOX', (0, 0), (-1, -1), 0.6, navy), ('INNERGRID', (0, 0), (-1, -1), 0.3, grid),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]
    for bx in range(len(bands)):
        style_cmds.append(('BACKGROUND', (3 + bx, 1), (3 + bx, 1), rl_color(band_rgb(bx, header=True))))

    row_i = 2
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
                                       rl_color(band_rgb(bx))))
                data.append(line)
            row_i += 1
        if len(branches) > 1:
            style_cmds.append(('SPAN', (0, span_start), (0, span_start + len(branches) - 1)))
        style_cmds.append(('LINEBELOW', (0, row_i - 1), (-1, row_i - 1), 0.8, navy))
    t = Table(data, colWidths=widths, repeatRows=2)
    t.setStyle(TableStyle(style_cmds))

    elems = [KeepTogether(banner('Subject-Wise Performance & Grade Percentage Breakdown')), t,
            Spacer(1, 4), Paragraph('— Not Offered', legendp)]

    # ---- Overall summary table (own page) ----
    sum_headers = _summary_headers(bands, pass_label)
    sum_rows = _summary_text_rows(result, pass_label)
    swidths = col_widths(sum_headers, sum_rows, grow_cols=list(range(2, 2 + len(bands))))
    span_label2 = f'{band_label} Percentage'.upper()
    srow0 = [Paragraph('BRANCH', navy_headp), Paragraph('TOTAL SUBJECT<br/>ENTRIES (N)', navy_headp),
            Paragraph(pdf_escape(span_label2), navy_headp)] + [''] * (len(bands) - 1) \
        + [Paragraph(pdf_escape(pass_label.upper()), navy_headp)]
    srow1 = ['', ''] + [Paragraph(f'{b} (%)', headp_for(band_rgb(i, header=True)))
                        for i, b in enumerate(bands)] + ['']
    sdata = [srow0, srow1]
    sstyle = [
        ('SPAN', (0, 0), (0, 1)), ('SPAN', (1, 0), (1, 1)),
        ('SPAN', (2, 0), (2 + len(bands) - 1, 0)),
        ('SPAN', (2 + len(bands), 0), (2 + len(bands), 1)),
        ('BACKGROUND', (0, 0), (1, 1), navy), ('BACKGROUND', (2, 0), (2 + len(bands) - 1, 0), navy),
        ('BACKGROUND', (2 + len(bands), 0), (2 + len(bands), 1), navy),
        ('FONTSIZE', (0, 0), (-1, -1), fs), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBELOW', (0, 1), (-1, 1), 1.1, navy),
        ('LINEBELOW', (0, 2), (-1, -1), 0.4, grid),
        ('BOX', (0, 0), (-1, -1), 0.6, navy), ('INNERGRID', (0, 0), (-1, -1), 0.3, grid),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]
    for bx in range(len(bands)):
        sstyle.append(('BACKGROUND', (2 + bx, 1), (2 + bx, 1), rl_color(band_rgb(bx, header=True))))
    for ri, br in enumerate(result['branches'], 2):
        s = result['summary'][br]
        line = [Paragraph(pdf_escape(br), cell), Paragraph(str(s['n']), cellc)]
        for bx, b in enumerate(bands):
            line.append(Paragraph(f"{s['pct'][b]}%", cellc))
            sstyle.append(('BACKGROUND', (2 + bx, ri), (2 + bx, ri), rl_color(band_rgb(bx))))
        line.append(Paragraph(f"<b>{s['pass_pct']}%</b> ({s['pass_n']})", cellc))
        sdata.append(line)
    st = Table(sdata, colWidths=swidths, repeatRows=2)
    st.setStyle(TableStyle(sstyle))

    elems.append(Spacer(1, 10))
    elems.append(KeepTogether(sub_banner(f'Overall {band_label} Percentage Summary by Branch')))
    elems.append(st)

    # ---- Composite ranking: a second summary, by different criteria (a
    # weighted-GPA-style composite score) ----
    ranking = result.get('ranking')
    if ranking:
        rc = result['ranking_criteria']
        crit_title_style = ParagraphStyle('critT', parent=styles['Normal'], fontSize=8, leading=10,
                                          textColor=colors.HexColor('#64748B'), fontName='Helvetica-Bold')
        crit_body_style = ParagraphStyle('critB', parent=styles['Normal'], fontSize=8.5, leading=12,
                                         textColor=colors.HexColor('#334155'), fontName='Helvetica')
        crit_rows = [[Paragraph('CRITERIA &amp; WEIGHTING SYSTEM', crit_title_style)]]
        for b in rc['bullets']:
            crit_rows.append([Paragraph('&#8226; ' + pdf_escape(b), crit_body_style)])
        crit_box = Table(crit_rows, colWidths=[avail])
        crit_box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
            ('BOX', (0, 0), (-1, -1), 0.6, grid),
            ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))

        rank_headers = ['Rank', 'Branch', 'Total Entries (N)', 'Weighted GPA', rc['top3_col'], rc['pass_col']]
        rank_text_rows = [[str(r['rank']), r['branch'], str(r['n']), f"{r['gpa']:.2f}",
                           f"{r['top3_pct']}%", f"{r['pass_pct']}%"] for r in ranking]
        rwidths = col_widths(rank_headers, rank_text_rows, grow_cols=[2, 3, 4, 5])
        rdata = [[Paragraph(h.upper(), navy_headp) for h in rank_headers]]
        rstyle = [
            ('BACKGROUND', (0, 0), (-1, 0), navy),
            ('FONTSIZE', (0, 0), (-1, -1), fs), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LINEBELOW', (0, 0), (-1, 0), 1.1, navy),
            ('LINEBELOW', (0, 1), (-1, -1), 0.4, grid),
            ('BOX', (0, 0), (-1, -1), 0.6, navy), ('INNERGRID', (0, 0), (-1, -1), 0.3, grid),
            ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]
        for r in ranking:
            rdata.append([Paragraph(str(r['rank']), cellc), Paragraph(pdf_escape(r['branch']), cell),
                         Paragraph(str(r['n']), cellc), Paragraph(f"<b>{r['gpa']:.2f}</b>", cellc),
                         Paragraph(f"{r['top3_pct']}%", cellc), Paragraph(f"{r['pass_pct']}%", cellc)])
        rt = Table(rdata, colWidths=rwidths, repeatRows=1)
        rt.setStyle(TableStyle(rstyle))

        elems.append(Spacer(1, 10))
        elems.append(KeepTogether(sub_banner(result['ranking_title'])))
        elems.append(crit_box)
        elems.append(Spacer(1, 6))
        elems.append(rt)

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

    school_name = (meta.get('school_name') or _school_name() or '').strip()
    navy = RGBColor(*NAVY_RGB)
    white = RGBColor(0xFF, 0xFF, 0xFF)
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
    avail_cm = sec.page_width.cm - sec.left_margin.cm - sec.right_margin.cm

    def shade(cell, hexcolor):
        cell._tc.get_or_add_tcPr().append(parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hexcolor.lstrip("#")}"/>'))

    def rgb_of(rgb):
        return RGBColor(*rgb)

    def banner(title_text):
        t = doc.add_table(rows=(2 if school_name else 1), cols=1)
        t.autofit = False
        t.columns[0].width = Cm(avail_cm)
        row = 0
        if school_name:
            c0 = t.rows[0].cells[0]
            c0.width = Cm(avail_cm)
            shade(c0, NAVY_HEX)
            p0 = c0.paragraphs[0]
            p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r0 = p0.add_run(school_name.upper())
            r0.bold = True; r0.font.size = Pt(15); r0.font.color.rgb = white
            row = 1
        c1 = t.rows[row].cells[0]
        c1.width = Cm(avail_cm)
        shade(c1, NAVY_HEX)
        p1 = c1.paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r1 = p1.add_run(title_text.upper())
        r1.bold = True; r1.font.size = Pt(12); r1.font.color.rgb = white
        doc.add_paragraph().paragraph_format.space_after = Pt(2)

    def sub_banner(title_text):
        # A slim single-line navy bar (no school name repeat) — the summary
        # table sits right under the main one on the same page, not its own.
        t = doc.add_table(rows=1, cols=1)
        t.autofit = False
        t.columns[0].width = Cm(avail_cm)
        c0 = t.rows[0].cells[0]
        c0.width = Cm(avail_cm)
        shade(c0, NAVY_HEX)
        p0 = c0.paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r0 = p0.add_run(title_text.upper())
        r0.bold = True; r0.font.size = Pt(12); r0.font.color.rgb = white
        doc.add_paragraph().paragraph_format.space_after = Pt(2)

    def set_cell(cell, text, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER, size=fs, italic=False, color=None):
        cell.text = str(text)
        pr = cell.paragraphs[0]
        pr.alignment = align
        if pr.runs:
            run = pr.runs[0]
            run.bold = bold; run.italic = italic; run.font.size = Pt(size)
            if color is not None:
                run.font.color.rgb = color

    banner('Subject-Wise Performance & Grade Percentage Breakdown')

    headers = _main_headers(bands)
    t = doc.add_table(rows=2, cols=len(headers))
    t.style = 'Table Grid'
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    r0, r1 = t.rows[0].cells, t.rows[1].cells
    for i, label in enumerate(('Subject', 'Branch', 'Candidates (N)')):
        set_cell(r0[i], label.upper(), bold=True, color=white)
        shade(r0[i], NAVY_HEX)
        merged = r0[i].merge(r1[i])
    span_label = f'{band_label} Percentage Breakdown'.upper()
    hdr_span = r0[3]
    for k in range(4, len(headers)):
        hdr_span = hdr_span.merge(r0[k])
    set_cell(hdr_span, span_label, bold=True, color=white)
    shade(hdr_span, NAVY_HEX)
    for bx, b in enumerate(bands):
        set_cell(r1[3 + bx], f'{b} (%)', bold=True, color=rgb_of(_text_on(band_rgb(bx, header=True))))
        shade(r1[3 + bx], band_hex(bx, header=True))

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
                set_cell(cells[0], subj, align=WD_ALIGN_PARAGRAPH.LEFT)
        if len(branches) > 1:
            top = t.rows[first_row_idx].cells[0]
            for k in range(1, len(branches)):
                top = top.merge(t.rows[first_row_idx + k].cells[0])
            top.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT

    _apply_docx_col_widths(t, _docx_col_widths(
        [[len(s) for s in result['subjects']], [len(b) for b in result['branches']]],
        ['Subject', 'Branch'], [4.2, 3.2], 'Candidates (N)', avail_cm, len(bands)))

    note = doc.add_paragraph()
    nr = note.add_run('— Not Offered')
    nr.italic = True; nr.font.size = Pt(8); nr.font.color.rgb = note_rgb

    sub_banner(f'Overall {band_label} Percentage Summary by Branch')
    sum_headers = _summary_headers(bands, pass_label)
    st = doc.add_table(rows=2, cols=len(sum_headers))
    st.style = 'Table Grid'
    st.alignment = WD_TABLE_ALIGNMENT.CENTER
    sr0, sr1 = st.rows[0].cells, st.rows[1].cells
    for i, label in enumerate(('Branch', 'Total Subject Entries (N)')):
        set_cell(sr0[i], label.upper(), bold=True, color=white)
        shade(sr0[i], NAVY_HEX)
        sr0[i].merge(sr1[i])
    span2 = f'{band_label} Percentage'.upper()
    hdr_span2 = sr0[2]
    for k in range(3, 2 + len(bands)):
        hdr_span2 = hdr_span2.merge(sr0[k])
    set_cell(hdr_span2, span2, bold=True, color=white)
    shade(hdr_span2, NAVY_HEX)
    set_cell(sr0[2 + len(bands)], pass_label.upper(), bold=True, color=white)
    shade(sr0[2 + len(bands)], NAVY_HEX)
    sr0[2 + len(bands)].merge(sr1[2 + len(bands)])
    for bx, b in enumerate(bands):
        set_cell(sr1[2 + bx], f'{b} (%)', bold=True, color=rgb_of(_text_on(band_rgb(bx, header=True))))
        shade(sr1[2 + bx], band_hex(bx, header=True))

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

    _apply_docx_col_widths(st, _docx_col_widths(
        [[len(b) for b in result['branches']]], ['Branch'], [3.2],
        'Total Subject Entries (N)', avail_cm, len(bands), tail_label=pass_label))

    # ---- Composite ranking: a second summary, by different criteria (a
    # weighted-GPA-style composite score) ----
    ranking = result.get('ranking')
    if ranking:
        rc = result['ranking_criteria']

        def criteria_box(title, bullets):
            bt = doc.add_table(rows=1, cols=1)
            bt.autofit = False
            bt.columns[0].width = Cm(avail_cm)
            c0 = bt.rows[0].cells[0]
            c0.width = Cm(avail_cm)
            shade(c0, 'F8FAFC')
            p0 = c0.paragraphs[0]
            r0 = p0.add_run(title.upper())
            r0.bold = True; r0.font.size = Pt(8); r0.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)
            for b in bullets:
                p = c0.add_paragraph()
                r = p.add_run('• ' + b)
                r.font.size = Pt(9); r.font.color.rgb = RGBColor(0x33, 0x41, 0x55)
            doc.add_paragraph().paragraph_format.space_after = Pt(2)

        sub_banner(result['ranking_title'])
        criteria_box('Criteria & Weighting System', rc['bullets'])

        rank_headers = ['Rank', 'Branch', 'Total Entries (N)', 'Weighted GPA', rc['top3_col'], rc['pass_col']]
        rt = doc.add_table(rows=1, cols=len(rank_headers))
        rt.style = 'Table Grid'
        rt.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, label in enumerate(rank_headers):
            set_cell(rt.rows[0].cells[i], label.upper(), bold=True, color=white)
            shade(rt.rows[0].cells[i], NAVY_HEX)

        for r in ranking:
            row = rt.add_row()
            cells = row.cells
            set_cell(cells[0], r['rank'])
            set_cell(cells[1], r['branch'], align=WD_ALIGN_PARAGRAPH.LEFT)
            set_cell(cells[2], r['n'])
            set_cell(cells[3], f"{r['gpa']:.2f}", bold=True)
            set_cell(cells[4], f"{r['top3_pct']}%")
            set_cell(cells[5], f"{r['pass_pct']}%")

        _apply_docx_col_widths(rt, _docx_col_widths(
            [[1 for _ in ranking], [len(r['branch']) for r in ranking]],
            ['Rank', 'Branch'], [1.6, 3.5], 'Total Entries (N)', avail_cm, 3))

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
    navy_fill = PatternFill('solid', fgColor=NAVY_HEX.lstrip('#'))
    white_font = Font(bold=True, color='FFFFFF')
    ctr = Alignment(horizontal='center', vertical='center', wrap_text=True)
    left = Alignment(horizontal='left', vertical='center')
    school_name = (meta.get('school_name') or _school_name() or '').strip()
    bands = result['bands']

    def band_font(bx):
        fg = _text_on(band_rgb(bx, header=True))
        return Font(bold=True, color='%02X%02X%02X' % fg)

    r = 1
    if school_name:
        c0 = ws.cell(row=r, column=1, value=school_name.upper())
        c0.font = Font(bold=True, size=14, color='FFFFFF')
        c0.fill = navy_fill; c0.alignment = ctr
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3 + len(bands))
        r += 1
    c1 = ws.cell(row=r, column=1, value='Subject-Wise Performance & Grade Percentage Breakdown'.upper())
    c1.font = Font(bold=True, size=12, color='FFFFFF')
    c1.fill = navy_fill; c1.alignment = ctr
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3 + len(bands))
    r += 2

    headers = _main_headers(bands)
    hrow = r
    for i, label in enumerate(('Subject', 'Branch', 'Candidates (N)')):
        c = ws.cell(row=hrow, column=i + 1, value=label.upper())
        c.font = white_font; c.fill = navy_fill; c.alignment = ctr
        ws.merge_cells(start_row=hrow, start_column=i + 1, end_row=hrow + 1, end_column=i + 1)
    span_cell = ws.cell(row=hrow, column=4, value=f'{band_label} Percentage Breakdown'.upper())
    span_cell.font = white_font; span_cell.fill = navy_fill; span_cell.alignment = ctr
    ws.merge_cells(start_row=hrow, start_column=4, end_row=hrow, end_column=3 + len(bands))
    for bx, b in enumerate(bands):
        c = ws.cell(row=hrow + 1, column=4 + bx, value=f'{b} (%)')
        c.font = band_font(bx); c.fill = PatternFill('solid', fgColor=band_hex(bx, header=True).lstrip('#'))
        c.alignment = ctr
    r = hrow + 2
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
        if len(branches) > 1:
            ws.merge_cells(start_row=subj_start, start_column=1, end_row=r - 1, end_column=1)
    ws.cell(row=r + 1, column=1, value='— Not Offered').font = Font(italic=True, color='94A3B8', size=9)
    ws.freeze_panes = ws.cell(row=data_start, column=1)
    # Content-tight columns — Subject/Branch/N stay as narrow as their actual
    # text (no dead whitespace), matching the reference layout; band columns
    # get a touch more room since they carry a "xx.x%" value under a header.
    subj_w = min(max((len(s) for s in result['subjects']), default=8) + 2, 26)
    br_w = min(max((len(b) for b in result['branches']), default=8) + 2, 18)
    ws.column_dimensions['A'].width = max(subj_w, len('Subject') + 2)
    ws.column_dimensions['B'].width = max(br_w, len('Branch') + 2)
    ws.column_dimensions['C'].width = len('Candidates (N)') + 1
    for c in range(4, len(headers) + 1):
        ws.column_dimensions[get_column_letter(c)].width = max(len(str(headers[c - 1])), 8) + 1
    ws.row_dimensions[hrow].height = 26

    ws2 = wb.create_sheet('Summary')
    r2 = 1
    c2 = ws2.cell(row=r2, column=1, value=f'Overall {band_label} Percentage Summary by Branch'.upper())
    c2.font = Font(bold=True, size=13, color='FFFFFF')
    c2.fill = navy_fill; c2.alignment = ctr
    sum_headers = _summary_headers(bands, pass_label)
    ws2.merge_cells(start_row=r2, start_column=1, end_row=r2, end_column=len(sum_headers))
    r2 += 2
    hrow2 = r2
    for i, label in enumerate(('Branch', 'Total Subject Entries (N)')):
        c = ws2.cell(row=hrow2, column=i + 1, value=label.upper())
        c.font = white_font; c.fill = navy_fill; c.alignment = ctr
        ws2.merge_cells(start_row=hrow2, start_column=i + 1, end_row=hrow2 + 1, end_column=i + 1)
    span2 = ws2.cell(row=hrow2, column=3, value=f'{band_label} Percentage'.upper())
    span2.font = white_font; span2.fill = navy_fill; span2.alignment = ctr
    ws2.merge_cells(start_row=hrow2, start_column=3, end_row=hrow2, end_column=2 + len(bands))
    passc = ws2.cell(row=hrow2, column=3 + len(bands), value=pass_label.upper())
    passc.font = white_font; passc.fill = navy_fill; passc.alignment = ctr
    ws2.merge_cells(start_row=hrow2, start_column=3 + len(bands), end_row=hrow2 + 1, end_column=3 + len(bands))
    for bx, b in enumerate(bands):
        c = ws2.cell(row=hrow2 + 1, column=3 + bx, value=f'{b} (%)')
        c.font = band_font(bx); c.fill = PatternFill('solid', fgColor=band_hex(bx, header=True).lstrip('#'))
        c.alignment = ctr
    r2 = hrow2 + 2
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
    br_w2 = min(max((len(b) for b in result['branches']), default=8) + 2, 18)
    ws2.column_dimensions['A'].width = max(br_w2, len('Branch') + 2)
    ws2.column_dimensions['B'].width = len('Total Subject Entries (N)') + 1
    for c in range(3, 2 + len(bands) + 1):
        ws2.column_dimensions[get_column_letter(c)].width = max(len(str(sum_headers[c - 1])), 8) + 1
    ws2.column_dimensions[get_column_letter(2 + len(bands) + 1)].width = len(pass_label) + 2
    ws2.row_dimensions[hrow2].height = 26

    # ---- Composite ranking: a second summary, by different criteria (a
    # weighted-GPA-style composite score) — its own sheet, own header. ----
    ranking = result.get('ranking')
    if ranking:
        rc = result['ranking_criteria']
        rank_headers = ['Rank', 'Branch', 'Total Entries (N)', 'Weighted GPA', rc['top3_col'], rc['pass_col']]
        ws3 = wb.create_sheet('Branch Ranking')
        crit_fill = PatternFill('solid', fgColor='F8FAFC')
        wrap_left = Alignment(horizontal='left', vertical='center', wrap_text=True)

        r3 = 1
        c3 = ws3.cell(row=r3, column=1, value=result['ranking_title'].upper())
        c3.font = Font(bold=True, size=13, color='FFFFFF')
        c3.fill = navy_fill; c3.alignment = ctr
        ws3.merge_cells(start_row=r3, start_column=1, end_row=r3, end_column=len(rank_headers))
        r3 += 2

        title_c = ws3.cell(row=r3, column=1, value='CRITERIA & WEIGHTING SYSTEM')
        title_c.font = Font(bold=True, size=9, color='64748B'); title_c.fill = crit_fill; title_c.alignment = left
        ws3.merge_cells(start_row=r3, start_column=1, end_row=r3, end_column=len(rank_headers))
        r3 += 1
        for b in rc['bullets']:
            bc = ws3.cell(row=r3, column=1, value='• ' + b)
            bc.font = Font(size=10, color='334155'); bc.fill = crit_fill; bc.alignment = wrap_left
            ws3.merge_cells(start_row=r3, start_column=1, end_row=r3, end_column=len(rank_headers))
            ws3.row_dimensions[r3].height = 24
            r3 += 1
        r3 += 1

        hrow3 = r3
        for i, label in enumerate(rank_headers):
            c = ws3.cell(row=hrow3, column=i + 1, value=label.upper())
            c.font = white_font; c.fill = navy_fill; c.alignment = ctr
        r3 = hrow3 + 1
        for rk in ranking:
            ws3.cell(row=r3, column=1, value=rk['rank']).alignment = ctr
            ws3.cell(row=r3, column=2, value=rk['branch']).alignment = left
            ws3.cell(row=r3, column=3, value=rk['n']).alignment = ctr
            gpa_c = ws3.cell(row=r3, column=4, value=rk['gpa']); gpa_c.alignment = ctr; gpa_c.font = Font(bold=True)
            top3_c = ws3.cell(row=r3, column=5, value=rk['top3_pct'] / 100)
            top3_c.number_format = '0.0%'; top3_c.alignment = ctr
            pass_c = ws3.cell(row=r3, column=6, value=rk['pass_pct'] / 100)
            pass_c.number_format = '0.0%'; pass_c.alignment = ctr
            r3 += 1

        ws3.column_dimensions['A'].width = len('Rank') + 4
        ws3.column_dimensions['B'].width = max((len(rk['branch']) for rk in ranking), default=8) + 4
        ws3.column_dimensions['C'].width = len('Total Entries (N)') + 2
        ws3.column_dimensions['D'].width = len('Weighted GPA') + 2
        ws3.column_dimensions['E'].width = max(len(rank_headers[4]), 10) + 2
        ws3.column_dimensions['F'].width = max(len(rank_headers[5]), 10) + 2
        ws3.row_dimensions[hrow3].height = 26

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
    NAVY = NAVY_RGB
    school_name = (meta.get('school_name') or _school_name() or '').strip()
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
    banner_l_f, banner_s_f, key_f = fnt(24, True), fnt(18, True), fnt(13)
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

    def draw_centered_wrapped(d, cx, cy_mid, maxw, text, f, fill, line_height):
        """Centered text at (cx, cy_mid); wraps onto a 2nd line (split on the
        widest-fitting word boundary) instead of truncating when it doesn't
        fit on one — matching how the PDF's Paragraph cells wrap."""
        text = str(text)
        if tw(text, f) <= maxw:
            d.text((cx - tw(text, f) / 2, cy_mid - line_height / 2), text, fill=fill, font=f)
            return
        words = text.split(' ')
        best = None
        for i in range(1, len(words)):
            l1, l2 = ' '.join(words[:i]), ' '.join(words[i:])
            if tw(l1, f) <= maxw and tw(l2, f) <= maxw:
                best = (l1, l2)
        if best is None:
            mid = max(1, len(words) // 2)
            best = (' '.join(words[:mid]) or words[0], ' '.join(words[mid:]))
        for i, ln in enumerate(best):
            txt = fit(ln, f, maxw)
            d.text((cx - tw(txt, f) / 2, cy_mid - line_height + i * line_height), txt, fill=fill, font=f)

    margin = 34 * S
    avail = PW * S - 2 * margin
    cpx, cpy = int(9 * S), int(7 * S)

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
    bottom_reserve = margin + int(30 * S)
    top_gap = int(12 * S)
    banner_line_h = int(30 * S)
    banner_h = banner_line_h * (2 if school_name else 1) + int(10 * S)

    pages = []

    def draw_banner(d, img, title_text):
        d.rectangle([margin, margin, margin + avail, margin + banner_h], fill=NAVY)
        ty = margin
        if school_name:
            txt = fit(school_name.upper(), banner_l_f, avail - int(20 * S))
            tx = margin + (avail - tw(txt, banner_l_f)) / 2
            d.text((tx, ty + (banner_line_h - int(24 * S)) / 2), txt, fill=(255, 255, 255), font=banner_l_f)
            ty += banner_line_h
        txt = fit(title_text.upper(), banner_s_f, avail - int(20 * S))
        tx = margin + (avail - tw(txt, banner_s_f)) / 2
        d.text((tx, ty + (banner_line_h - int(18 * S)) / 2), txt, fill=(255, 255, 255), font=banner_s_f)
        return margin + banner_h

    def draw_slim_banner(d, y, text):
        # A slim single-line navy bar (no school name repeat) — used for the
        # summary section when it continues on the same page as the main table.
        bh = banner_line_h
        d.rectangle([margin, y, margin + avail, y + bh], fill=NAVY)
        txt = fit(text.upper(), banner_s_f, avail - int(20 * S))
        tx = margin + (avail - tw(txt, banner_s_f)) / 2
        d.text((tx, y + (bh - int(18 * S)) / 2), txt, fill=(255, 255, 255), font=banner_s_f)
        return y + bh + int(10 * S)

    def new_page(title_text, draw_mast):
        img = Image.new('RGB', (PW * S, PH * S), C['white'])
        d = ImageDraw.Draw(img)
        if draw_mast:
            y0 = draw_banner(d, img, title_text) + int(14 * S)
        else:
            y0 = margin + top_gap
        return img, d, y0

    def save_page(img):
        out = io.BytesIO()
        img.resize((PW, PH), Image.LANCZOS).save(out, format='PNG')
        pages.append(out.getvalue())

    # ---- Main breakdown table (paginates whole subject-blocks) ----
    headers = _main_headers(bands)
    col_w = measure(headers, _main_text_rows(result), grow_cols=list(range(3, 3 + len(bands))))
    table_w = sum(col_w)
    page_title = 'Subject-Wise Performance & Grade Percentage Breakdown'
    span_label = f'{band_label} Percentage Breakdown'.upper()

    def draw_header_rows(d, y0):
        # row 0: Subject/Branch/N (navy, tall enough for 2 rows) + spanning label
        d.rectangle([margin, y0, margin + col_w[0] + col_w[1] + col_w[2], y0 + header_h * 2], fill=NAVY)
        band_x0 = margin + col_w[0] + col_w[1] + col_w[2]
        d.rectangle([band_x0, y0, margin + table_w, y0 + header_h], fill=NAVY)
        x = margin
        for j, label in enumerate(('Subject', 'Branch', 'Candidates (N)')):
            draw_centered_wrapped(d, x + col_w[j] / 2, y0 + header_h, col_w[j] - 2 * cpx,
                                 label.upper(), body_b, (255, 255, 255), line_h)
            x += col_w[j]
        txt = fit(span_label, body_b, table_w - col_w[0] - col_w[1] - col_w[2] - 2 * cpx)
        d.text((band_x0 + (margin + table_w - band_x0 - tw(txt, body_b)) / 2,
               y0 + (header_h - line_h) / 2), txt, fill=(255, 255, 255), font=body_b)
        # row 1: individual band headers, colour-coded
        y1 = y0 + header_h
        x = band_x0
        for j in range(3, len(headers)):
            bx = j - 3
            rgb = band_rgb(bx, header=True)
            fg = _text_on(rgb)
            d.rectangle([x, y1, x + col_w[j], y1 + header_h], fill=rgb)
            txt = fit(headers[j], body_b, col_w[j] - 2 * cpx)
            d.text((x + (col_w[j] - tw(txt, body_b)) / 2, y1 + (header_h - line_h) / 2),
                   txt, fill=fg, font=body_b)
            x += col_w[j]
        d.rectangle([margin, y0, margin + table_w, y0 + header_h * 2], outline=NAVY, width=2)
        return y0 + header_h * 2

    def grid_lines(d, y0, y):
        d.rectangle([margin, y0, margin + table_w, y], outline=C['line'], width=1)
        x = margin
        for j in range(len(headers) - 1):
            x += col_w[j]
            d.line([x, y0, x, y], fill=C['line'], width=1)

    img, d, y0 = new_page(page_title, draw_mast=True)
    y = draw_header_rows(d, y0)
    max_y = PH * S - bottom_reserve

    for subj in result['subjects']:
        branches = result['branches']
        need_h = row_h * len(branches)
        if y + need_h > max_y and y > y0 + header_h * 2:
            grid_lines(d, y0, y)
            save_page(img)
            img, d, y0 = new_page(page_title, draw_mast=False)
            y = draw_header_rows(d, y0)
        subj_top = y
        for ri, br in enumerate(branches):
            cell_ = result['table'][subj][br]
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
               fit(subj, body, col_w[0] - 2 * cpx), fill=C['text'], font=body)
        d.line([margin, y, margin + table_w, y], fill=NAVY, width=2)

    grid_lines(d, y0, y)
    legend_y = y + int(10 * S)
    content_end_y = legend_y
    if legend_y + key_f.size < max_y:
        d.text((margin, legend_y), '— Not Offered', fill=C['muted'], font=key_f)
        content_end_y = legend_y + key_f.size + int(8 * S)

    # ---- Overall summary — right under the main table on the same A4 page
    # when it fits (matching the reference sheet); only a fresh page if not. ----
    sum_headers = _summary_headers(bands, pass_label)
    sum_rows = _summary_text_rows(result, pass_label)
    scol_w = measure(sum_headers, sum_rows, grow_cols=list(range(2, 2 + len(bands))))
    stable_w = sum(scol_w)
    slim_gap = int(14 * S)
    summary_h = banner_line_h + int(10 * S) + slim_gap + header_h * 2 + row_h * len(result['branches'])

    if content_end_y + summary_h <= max_y:
        simg, sd = img, d
        sy0 = draw_slim_banner(sd, content_end_y + slim_gap,
                               f'Overall {band_label} Percentage Summary by Branch')
    else:
        save_page(img)
        simg, sd, sy0b = new_page(page_title, draw_mast=False)
        sy0 = draw_slim_banner(sd, sy0b, f'Overall {band_label} Percentage Summary by Branch')

    band_x0 = margin + scol_w[0] + scol_w[1]
    sd.rectangle([margin, sy0, band_x0, sy0 + header_h * 2], fill=NAVY)
    sd.rectangle([band_x0, sy0, margin + stable_w - scol_w[-1], sy0 + header_h], fill=NAVY)
    sd.rectangle([margin + stable_w - scol_w[-1], sy0, margin + stable_w, sy0 + header_h * 2], fill=NAVY)
    x = margin
    for j, label in enumerate(('Branch', 'Total Subject Entries (N)')):
        draw_centered_wrapped(d=sd, cx=x + scol_w[j] / 2, cy_mid=sy0 + header_h, maxw=scol_w[j] - 2 * cpx,
                             text=label.upper(), f=body_b, fill=(255, 255, 255), line_height=line_h)
        x += scol_w[j]
    span2 = f'{band_label} Percentage'.upper()
    txt = fit(span2, body_b, (margin + stable_w - scol_w[-1]) - band_x0 - 2 * cpx)
    sd.text((band_x0 + ((margin + stable_w - scol_w[-1]) - band_x0 - tw(txt, body_b)) / 2,
            sy0 + (header_h - line_h) / 2), txt, fill=(255, 255, 255), font=body_b)
    draw_centered_wrapped(d=sd, cx=margin + stable_w - scol_w[-1] / 2, cy_mid=sy0 + header_h,
                         maxw=scol_w[-1] - 2 * cpx, text=pass_label.upper(), f=body_b,
                         fill=(255, 255, 255), line_height=line_h)
    sy1 = sy0 + header_h
    x = band_x0
    for bx, b in enumerate(bands):
        bw = scol_w[2 + bx]
        rgb = band_rgb(bx, header=True)
        fg = _text_on(rgb)
        sd.rectangle([x, sy1, x + bw, sy1 + header_h], fill=rgb)
        txt = fit(f'{b} (%)', body_b, bw - 2 * cpx)
        sd.text((x + (bw - tw(txt, body_b)) / 2, sy1 + (header_h - line_h) / 2), txt, fill=fg, font=body_b)
        x += bw
    sd.rectangle([margin, sy0, margin + stable_w, sy0 + header_h * 2], outline=NAVY, width=2)
    sy = sy0 + header_h * 2
    for i, br in enumerate(result['branches']):
        s = result['summary'][br]
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

    # ---- Composite ranking: a second summary, by different criteria (a
    # weighted-GPA-style composite score), continuing on this page if it
    # fits, otherwise starting a fresh one. ----
    ranking = result.get('ranking')
    if ranking:
        rc = result['ranking_criteria']
        rank_headers = ['Rank', 'Branch', 'Total Entries (N)', 'Weighted GPA', rc['top3_col'], rc['pass_col']]
        rank_text_rows = [[str(rk['rank']), rk['branch'], str(rk['n']), f"{rk['gpa']:.2f}",
                           f"{rk['top3_pct']}%", f"{rk['pass_pct']}%"] for rk in ranking]
        rcol_w = measure(rank_headers, rank_text_rows, grow_cols=[2, 3, 4, 5])
        rcol_w[0] += int(6 * S)  # a little slack so "RANK" never brushes the truncation edge
        rtable_w = sum(rcol_w)

        def wrap_lines(text, f, maxw):
            words = str(text).split(' ')
            out, cur = [], ''
            for w in words:
                trial = (cur + ' ' + w).strip()
                if not cur or tw(trial, f) <= maxw:
                    cur = trial
                else:
                    out.append(cur)
                    cur = w
            if cur:
                out.append(cur)
            return out

        crit_pad = int(10 * S)
        crit_maxw = avail - 2 * crit_pad
        crit_title_f = fnt(11, True)
        crit_body_f = fnt(11)
        crit_lh = tmp.textbbox((0, 0), 'Ay', font=crit_body_f)[3] + int(3 * S)
        crit_lines = [('CRITERIA & WEIGHTING SYSTEM', crit_title_f, (100, 116, 139))]
        for b in rc['bullets']:
            for wln in wrap_lines('• ' + b, crit_body_f, crit_maxw):
                crit_lines.append((wln, crit_body_f, (51, 65, 85)))
        crit_h = crit_pad * 2 + crit_lh * len(crit_lines)

        def draw_rank_header(d, y):
            d.rectangle([margin, y, margin + rtable_w, y + header_h], fill=NAVY)
            x = margin
            for j, h in enumerate(rank_headers):
                draw_centered_wrapped(d, x + rcol_w[j] / 2, y + header_h / 2, rcol_w[j] - 2 * cpx,
                                     h.upper(), body_b, (255, 255, 255), line_h)
                x += rcol_w[j]
            d.rectangle([margin, y, margin + rtable_w, y + header_h], outline=NAVY, width=2)
            return y + header_h

        def close_rank_segment(d, top, bottom):
            d.rectangle([margin, top, margin + rtable_w, bottom], outline=C['line'], width=1)
            x = margin
            for j in range(len(rank_headers) - 1):
                x += rcol_w[j]
                d.line([x, top, x, bottom], fill=C['line'], width=1)

        # room needed for the section heading + criteria box + header + at
        # least one data row, before it's worth starting on this page at all
        header_block_h = banner_line_h + int(10 * S) + slim_gap + crit_h + int(8 * S) + header_h
        if sy + header_block_h + row_h <= max_y:
            rimg, rd = simg, sd
            ry0 = draw_slim_banner(rd, sy + slim_gap, result['ranking_title'])
        else:
            save_page(simg)
            rimg, rd, ry0b = new_page(page_title, draw_mast=False)
            ry0 = draw_slim_banner(rd, ry0b, result['ranking_title'])

        box_y = ry0
        rd.rectangle([margin, box_y, margin + avail, box_y + crit_h],
                    fill=(248, 250, 252), outline=(185, 194, 206), width=1)
        ty = box_y + crit_pad
        for text, f, color in crit_lines:
            rd.text((margin + crit_pad, ty), text, fill=color, font=f)
            ty += crit_lh
        rtop = box_y + crit_h + int(8 * S)
        ry = draw_rank_header(rd, rtop)
        seg_top = rtop

        for rk in ranking:
            if ry + row_h > max_y:
                close_rank_segment(rd, seg_top, ry)
                save_page(rimg)
                rimg, rd, ry0b = new_page(page_title, draw_mast=False)
                ry = draw_rank_header(rd, ry0b)
                seg_top = ry0b
            x = margin
            vals = [str(rk['rank']), rk['branch'], str(rk['n']), f"{rk['gpa']:.2f}",
                   f"{rk['top3_pct']}%", f"{rk['pass_pct']}%"]
            for j, val in enumerate(vals):
                f_ = body_b if j == 3 else body
                if j == 1:
                    rd.text((x + cpx, ry + cpy), fit(val, body, rcol_w[j] - 2 * cpx), fill=C['text'], font=body)
                else:
                    tx = x + (rcol_w[j] - tw(val, f_)) / 2
                    rd.text((tx, ry + cpy), val, fill=C['text'], font=f_)
                x += rcol_w[j]
            rd.line([margin, ry, margin + rtable_w, ry], fill=C['line'], width=1)
            ry += row_h
        close_rank_segment(rd, seg_top, ry)

        save_page(rimg)
    else:
        save_page(simg)

    return pages


def grade_breakdown_image_export(meta, result, band_label, pass_label):
    """Returns (bytes, mimetype, ext) — a single HD PNG, or a zip of pages."""
    pages = grade_breakdown_png_pages(meta, result, band_label, pass_label)
    if len(pages) == 1:
        return pages[0], 'image/png', 'png'
    return zip_pngs(pages, base='grade_breakdown'), 'application/zip', 'zip'
