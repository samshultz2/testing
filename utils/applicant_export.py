"""Branded single-applicant record sheet — PDF (reportlab) and Word (python-docx).

Shares the visual language of the other exports: a masthead with the school
logo / name / address / motto, a title band, and labelled sections
(Applicant, Application, Parent/Guardian, Emergency Contact, Notes).

``record`` shape (built by the route)::

    {
      'title': 'Applicant Record',
      'name': 'Surname First Middle',
      'meta': [('Application No', 'APP2026-0001'), ('Status', 'Applied')],
      'sections': [('Applicant', [('Gender', 'Male'), ...]), ...],
    }
"""
import io
import os

from utils import timeutil
from utils.student_export import (NAVY, GOLD, INK, MUTED, LINE, PANEL,
                                  _FONT_REG, _FONT_BOLD, _FONT_ITAL)


def applicant_pdf(record, school):
    """A4-portrait applicant record sheet built with reportlab. Returns bytes."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Table,
                                    TableStyle, Paragraph, Spacer, KeepTogether)
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    base, boldf, obl = 'Helvetica', 'Helvetica-Bold', 'Helvetica-Oblique'
    try:
        pdfmetrics.registerFont(TTFont('ApBody', _FONT_REG)); base = 'ApBody'
        pdfmetrics.registerFont(TTFont('ApBody-Bold', _FONT_BOLD)); boldf = 'ApBody-Bold'
        pdfmetrics.registerFont(TTFont('ApBody-Obl', _FONT_ITAL)); obl = 'ApBody-Obl'
    except Exception:
        pass

    PW, PH = A4
    margin = 14 * mm
    mast_h = 40 * mm
    avail = PW - 2 * margin

    lab = ParagraphStyle('lab', fontName=boldf, fontSize=10, leading=13,
                         textColor=colors.HexColor(MUTED))
    val = ParagraphStyle('val', fontName=base, fontSize=11.5, leading=15,
                         textColor=colors.HexColor(INK))
    sec = ParagraphStyle('sec', fontName=boldf, fontSize=12.5, leading=16,
                         textColor=colors.HexColor(NAVY))

    def _draw_masthead(cv, doc):
        from reportlab.pdfbase.pdfmetrics import stringWidth
        cv.setStrokeColor(colors.HexColor(GOLD)); cv.setLineWidth(1.6)
        cv.roundRect(margin * 0.5, margin * 0.5, PW - margin, PH - margin, 9, stroke=1, fill=0)
        top = PH - margin - 3 * mm
        x = margin + 4 * mm
        logo = (school or {}).get('logo_path')
        lx = x
        if logo and os.path.exists(logo):
            try:
                from reportlab.lib.utils import ImageReader
                ir = ImageReader(logo); iw, ih = ir.getSize()
                h = 22 * mm; w = h * (iw / ih) if ih else 22 * mm
                cv.drawImage(ir, x, top - h, width=min(w, 24 * mm), height=h,
                             mask='auto', preserveAspectRatio=True)
                lx = x + min(w, 24 * mm) + 5 * mm
            except Exception:
                lx = x
        name = ((school or {}).get('name') or 'School').upper()
        size = 21
        while size > 12 and stringWidth(name, boldf, size) > (avail - (lx - x)):
            size -= 1
        cv.setFillColor(colors.HexColor(NAVY)); cv.setFont(boldf, size)
        cv.drawString(lx, top - 7 * mm, name)
        cv.setFillColor(colors.HexColor(INK)); cv.setFont(base, 9.5)
        addr = (school or {}).get('address') or ''
        if addr:
            cv.drawString(lx, top - 12.5 * mm, addr[:110])
        contact = '    '.join(p for p in [(school or {}).get('phone') or '',
                                          (school or {}).get('email') or ''] if p)
        if contact:
            cv.drawString(lx, top - 17 * mm, contact[:110])
        motto = (school or {}).get('motto') or ''
        if motto:
            cv.setFillColor(colors.HexColor(GOLD)); cv.setFont(obl, 10)
            cv.drawString(lx, top - 22 * mm, ('—  ' + motto + '  —')[:110])
        # passport photo (top-right corner of the first page)
        pb = record.get('photo_bytes')
        if pb and doc.page == 1:
            try:
                from reportlab.lib.utils import ImageReader
                pw_, ph_ = 24 * mm, 30 * mm
                px = PW - margin - 4 * mm - pw_
                cv.drawImage(ImageReader(io.BytesIO(pb)), px, top - ph_, width=pw_, height=ph_,
                             preserveAspectRatio=True, mask='auto')
                cv.setStrokeColor(colors.HexColor(LINE)); cv.setLineWidth(0.6)
                cv.rect(px, top - ph_, pw_, ph_, stroke=1, fill=0)
            except Exception:
                pass
        # gold divider under the masthead
        cv.setStrokeColor(colors.HexColor(GOLD)); cv.setLineWidth(1)
        cv.line(margin, PH - margin - mast_h + 4 * mm, PW - margin, PH - margin - mast_h + 4 * mm)
        # footer
        cv.setStrokeColor(colors.HexColor(LINE)); cv.setLineWidth(0.6)
        cv.line(margin, margin + 8 * mm, PW - margin, margin + 8 * mm)
        cv.setFillColor(colors.HexColor(MUTED)); cv.setFont(obl, 8)
        cv.drawString(margin, margin + 4 * mm, 'Generated %s · system-generated and confidential.'
                      % timeutil.today().strftime('%d %b %Y'))
        cv.drawRightString(PW - margin, margin + 4 * mm, 'Page %d' % doc.page)

    story = []
    # Title band + name + meta
    title = record.get('title') or 'Applicant Record'
    story.append(Paragraph('<font color="%s"><b>%s</b></font>' % (NAVY, title),
                           ParagraphStyle('t', fontName=boldf, fontSize=16, leading=20)))
    story.append(Paragraph('<font color="%s">%s</font>' % (INK, record.get('name') or ''),
                           ParagraphStyle('n', fontName=base, fontSize=13, leading=17)))
    meta = record.get('meta') or []
    if meta:
        cells = [[Paragraph('<font color="%s"><b>%s</b></font>&nbsp;&nbsp;%s'
                            % (MUTED, k, v), val) for k, v in meta]]
        mt = Table(cells, colWidths=[avail / max(1, len(meta))] * len(meta))
        mt.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(PANEL)),
            ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor(LINE)),
            ('INNERGRID', (0, 0), (-1, -1), 0.6, colors.HexColor(LINE)),
            ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LEFTPADDING', (0, 0), (-1, -1), 9), ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ]))
        story.append(Spacer(1, 5 * mm)); story.append(mt)

    for heading, rows in record.get('sections') or []:
        rows = [r for r in rows if r]
        if not rows:
            continue
        block = [Spacer(1, 6 * mm), Paragraph(heading, sec), Spacer(1, 2 * mm)]
        data = [[Paragraph(str(k), lab), Paragraph('' if v is None else str(v), val)] for k, v in rows]
        t = Table(data, colWidths=[46 * mm, avail - 46 * mm])
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 2), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('LINEBELOW', (0, 0), (-1, -2), 0.4, colors.HexColor(LINE)),
        ]))
        block.append(t)
        story.append(KeepTogether(block))

    buf = io.BytesIO()
    frame = Frame(margin, margin + 10 * mm, avail, PH - mast_h - margin - 12 * mm,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=margin, rightMargin=margin,
                          topMargin=margin, bottomMargin=margin)
    doc.addPageTemplates([PageTemplate(id='main', frames=[frame], onPage=_draw_masthead)])
    doc.build(story)
    return buf.getvalue()


def applicant_docx(record, school, filename='applicant.docx'):
    """A branded applicant record sheet as .docx. Returns a Flask Response."""
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import nsdecls
    from docx.oxml import parse_xml
    from io import BytesIO
    from flask import Response

    navy = RGBColor(0x1E, 0x2A, 0x4A); gold = RGBColor(0xB8, 0x86, 0x2B)
    muted = RGBColor(0x6B, 0x72, 0x80)

    doc = Document()
    section = doc.sections[0]
    section.left_margin = section.right_margin = Cm(1.6)
    section.top_margin = section.bottom_margin = Cm(1.3)

    logo = (school or {}).get('logo_path')
    if logo and os.path.exists(logo):
        try:
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run().add_picture(logo, height=Cm(1.5))
        except Exception:
            pass
    nm = doc.add_paragraph(); nm.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = nm.add_run(((school or {}).get('name') or 'School').upper())
    r.bold = True; r.font.size = Pt(18); r.font.color.rgb = navy
    line2 = '    '.join(x for x in [(school or {}).get('address') or '',
                                    (school or {}).get('phone') or '',
                                    (school or {}).get('email') or ''] if x)
    if line2:
        sp = doc.add_paragraph(); sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sp.add_run(line2).font.size = Pt(9.5)
    if (school or {}).get('motto'):
        mp = doc.add_paragraph(); mp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        rm = mp.add_run('—  ' + school['motto'] + '  —'); rm.italic = True
        rm.font.size = Pt(10); rm.font.color.rgb = gold

    tp = doc.add_paragraph(); tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    tr = tp.add_run(record.get('title') or 'Applicant Record')
    tr.bold = True; tr.font.size = Pt(15); tr.font.color.rgb = navy
    if record.get('name'):
        npar = doc.add_paragraph(); npar.alignment = WD_ALIGN_PARAGRAPH.CENTER
        npar.add_run(record['name']).font.size = Pt(12)
    meta = record.get('meta') or []
    if meta:
        mp2 = doc.add_paragraph(); mp2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        mr = mp2.add_run('    '.join('%s: %s' % (k, v) for k, v in meta))
        mr.font.size = Pt(10); mr.font.color.rgb = muted

    for heading, rows in record.get('sections') or []:
        rows = [r for r in rows if r]
        if not rows:
            continue
        hp = doc.add_paragraph(); hr = hp.add_run(heading)
        hr.bold = True; hr.font.size = Pt(12); hr.font.color.rgb = navy
        table = doc.add_table(rows=0, cols=2)
        table.style = 'Table Grid'
        table.alignment = WD_TABLE_ALIGNMENT.LEFT
        for k, v in rows:
            row = table.add_row().cells
            row[0].width = Cm(5.5); row[1].width = Cm(12.5)
            kp = row[0].paragraphs[0]; kr = kp.add_run(str(k))
            kr.bold = True; kr.font.size = Pt(9.5); kr.font.color.rgb = muted
            kp2 = row[1].paragraphs[0]; kr2 = kp2.add_run('' if v is None else str(v))
            kr2.font.size = Pt(10.5)
            row[0]._tc.get_or_add_tcPr().append(parse_xml(f'<w:shd {nsdecls("w")} w:fill="F7F8FA"/>'))
        doc.add_paragraph()

    foot = doc.add_paragraph('Generated %s · system-generated and confidential.'
                             % timeutil.today().strftime('%d %b %Y'))
    if foot.runs:
        foot.runs[0].italic = True; foot.runs[0].font.size = Pt(8)
        foot.runs[0].font.color.rgb = muted

    out = BytesIO(); doc.save(out); out.seek(0)
    return Response(out.getvalue(),
                    mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    headers={'Content-Disposition': 'attachment; filename=%s' % filename})


def applicant_blank_pdf(school, bw=False):
    """A branded, *fillable* blank application form (interactive AcroForm PDF)
    on one A4 page — type into it on screen, or print it and fill it by hand.

    ``bw=False`` is the colour version (navy / gold accents, soft field fills).
    ``bw=True`` is the black-and-white print version: black ink, strong field
    borders, white fills and a greyscale logo, so it stays crisp on a mono
    printer or photocopier. Returns bytes."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas as _canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.pdfmetrics import stringWidth

    base, boldf, obl = 'Helvetica', 'Helvetica-Bold', 'Helvetica-Oblique'
    try:
        pdfmetrics.registerFont(TTFont('ApBody', _FONT_REG)); base = 'ApBody'
        pdfmetrics.registerFont(TTFont('ApBody-Bold', _FONT_BOLD)); boldf = 'ApBody-Bold'
        pdfmetrics.registerFont(TTFont('ApBody-Obl', _FONT_ITAL)); obl = 'ApBody-Obl'
    except Exception:
        pass

    school = school or {}
    PW, PH = A4
    margin = 14 * mm
    avail = PW - 2 * margin
    if bw:
        navy = ink = colors.black
        gold = colors.HexColor('#222222')
        muted = colors.HexColor('#2b2b2b')
        line = colors.HexColor('#6b6b6b')
        fill = colors.white
        border, border_w = colors.HexColor('#1a1a1a'), 0.9
        office_bg = colors.white
    else:
        navy = colors.HexColor(NAVY); gold = colors.HexColor(GOLD)
        ink = colors.HexColor(INK); muted = colors.HexColor(MUTED)
        line = colors.HexColor(LINE)
        fill = colors.HexColor('#FBFCFE')
        border, border_w = colors.HexColor('#AEB9CC'), 0.8
        office_bg = colors.HexColor('#F6F1E6')

    buf = io.BytesIO()
    c = _canvas.Canvas(buf, pagesize=A4)
    c.setTitle('Application Form%s — %s' % (' (black & white)' if bw else '', school.get('name') or 'School'))
    form = c.acroForm
    st = {'y': 0, 'n': 0, 'page': 0}

    def logo_reader():
        path = school.get('logo_path')
        if not path or not os.path.exists(path):
            return None
        from reportlab.lib.utils import ImageReader
        if not bw:
            return ImageReader(path)
        try:  # greyscale logo for the black & white version
            from PIL import Image
            im = Image.open(path)
            if im.mode in ('RGBA', 'LA', 'P'):
                im = im.convert('RGBA')
                bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
                bg.alpha_composite(im); im = bg
            g = io.BytesIO(); im.convert('L').save(g, format='PNG'); g.seek(0)
            return ImageReader(g)
        except Exception:
            return ImageReader(path)

    def footer():
        c.setStrokeColor(line); c.setLineWidth(0.5)
        c.line(margin, margin + 6 * mm, PW - margin, margin + 6 * mm)
        c.setFillColor(muted); c.setFont(obl, 7.5)
        c.drawString(margin, margin + 2.6 * mm, 'Application form · %s' % (school.get('name') or 'School'))
        c.drawRightString(PW - margin, margin + 2.6 * mm, 'Page %d' % st['page'])

    def new_page(first=False):
        st['page'] += 1
        c.setStrokeColor(gold); c.setLineWidth(1.4 if not bw else 1)
        c.roundRect(margin * 0.5, margin * 0.5, PW - margin, PH - margin, 8, stroke=1, fill=0)
        top = PH - margin - 2 * mm
        if first:
            x = margin
            lx = x
            ir = None
            try:
                ir = logo_reader()
            except Exception:
                ir = None
            if ir is not None:
                iw, ih = ir.getSize()
                h = 21 * mm
                w = min(h * (iw / ih) if ih else h, 24 * mm)
                c.drawImage(ir, x, top - h, width=w, height=h, mask='auto', preserveAspectRatio=True)
                lx = x + w + 5 * mm
            name = (school.get('name') or 'School').upper()
            size = 19
            while size > 12 and stringWidth(name, boldf, size) > (PW - margin - lx):
                size -= 1
            c.setFillColor(navy); c.setFont(boldf, size)
            c.drawString(lx, top - 6 * mm, name)
            c.setFillColor(ink); c.setFont(base, 8.8)
            yy = top - 11 * mm
            if school.get('address'):
                c.drawString(lx, yy, school['address'][:115]); yy -= 4 * mm
            contact = '   ·   '.join(p for p in [school.get('phone') or '', school.get('email') or ''] if p)
            if contact:
                c.drawString(lx, yy, contact[:115]); yy -= 4 * mm
            if school.get('motto'):
                c.setFillColor(gold); c.setFont(obl, 9)
                c.drawString(lx, yy - 0.5 * mm, school['motto'][:110])
            # title band
            ty = top - 27.5 * mm
            if bw:
                c.setStrokeColor(colors.black); c.setLineWidth(1.2)
                c.line(margin, ty - 2.5 * mm, PW - margin, ty - 2.5 * mm)
            else:
                c.setFillColor(navy)
                c.roundRect(margin, ty - 3 * mm, avail, 9.5 * mm, 2.5 * mm, stroke=0, fill=1)
            c.setFillColor(colors.white if not bw else colors.black); c.setFont(boldf, 13.5)
            tx = margin + (3.5 * mm if not bw else 0)
            c.drawString(tx, ty, 'APPLICATION FORM')
            c.setFont(obl, 8.3)
            c.drawRightString(PW - margin - (3.5 * mm if not bw else 0), ty + 0.3 * mm,
                              'Please write in BLOCK LETTERS and tick the boxes that apply')
            st['y'] = ty - 6 * mm
        else:
            st['y'] = top
        footer()

    def ensure(space):
        if st.get('fixed'):          # inside a box already sized to fit
            return
        if st['y'] - space < margin + 10 * mm:
            c.showPage(); new_page(first=False)

    def heading(text, num):
        ensure(16 * mm)
        y = st['y'] - 4.2 * mm
        if bw:
            c.setFillColor(colors.black)
            c.circle(margin + 2.3 * mm, y + 1.2 * mm, 2.3 * mm, stroke=0, fill=1)
        else:
            c.setFillColor(gold)
            c.circle(margin + 2.3 * mm, y + 1.2 * mm, 2.3 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white); c.setFont(boldf, 7.5)
        c.drawCentredString(margin + 2.3 * mm, y + 0.25 * mm, str(num))
        c.setFillColor(navy); c.setFont(boldf, 11)
        c.drawString(margin + 6.5 * mm, y, text)
        c.setStrokeColor(line); c.setLineWidth(0.5)
        c.line(margin + 6.5 * mm + stringWidth(text, boldf, 11) + 3 * mm, y + 1.2 * mm, PW - margin, y + 1.2 * mm)
        st['y'] -= 6.8 * mm

    FH = 7.2 * mm          # field height
    LAB = 3.6 * mm         # label band above a field
    GAP_Y = 2.6 * mm       # space under a row

    def label(text, x, y):
        c.setFillColor(muted); c.setFont(boldf, 7.3)
        c.drawString(x, y - 2.6 * mm, text.upper())

    def textbox(name, tip, x, y, w, h, multiline=False, size=10.5, maxlen=None):
        st['n'] += 1
        kw = dict(name='%s_%d' % (name, st['n']), tooltip=tip, x=x, y=y, width=w, height=h,
                  borderColor=border, fillColor=fill, textColor=ink, borderWidth=border_w,
                  forceBorder=True, fontSize=size, fieldFlags=('multiline' if multiline else ''))
        if maxlen:
            kw['maxlen'] = maxlen
        form.textfield(**kw)

    def checks(name, opts, x, y):
        """Tick boxes on one line, starting at x, vertically centred in a field row."""
        cx = x
        for o in opts:
            st['n'] += 1
            sz = 4.6 * mm
            form.checkbox(name='%s_%d' % (name, st['n']), tooltip=o, x=cx, y=y + (FH - sz) / 2, size=sz,
                          borderColor=border, fillColor=fill, textColor=ink, borderWidth=border_w,
                          buttonStyle='check', forceBorder=True)
            c.setFillColor(ink); c.setFont(base, 9.5)
            c.drawString(cx + sz + 1.6 * mm, y + FH / 2 - 1.2 * mm, o)
            cx += sz + 1.6 * mm + stringWidth(o, base, 9.5) + 6 * mm

    def cell(f, x, w):
        """One labelled cell. f = (label, weight, kind[, options]); kind: text|big|checks|date."""
        lab, kind = f[0], (f[2] if len(f) > 2 else 'text')
        y_top = st['y']
        label(lab + (' (DD / MM / YYYY)' if kind == 'date' else ''), x, y_top)
        h = FH * 1.55 if kind == 'big' else FH
        fy = y_top - LAB - h
        key = ''.join(ch for ch in lab.lower() if ch.isalnum())[:16] or 'f'
        if kind == 'checks':
            checks(key, f[3], x, fy)
        elif kind == 'date':
            parts = [('DD', 9 * mm, 2), ('MM', 9 * mm, 2), ('YYYY', 15 * mm, 4)]
            cx = x
            for i, (tip, pw, ml) in enumerate(parts):
                textbox(key, '%s — %s' % (lab, tip), cx, fy, pw, h, maxlen=ml)
                cx += pw
                if i < 2:
                    c.setFillColor(muted); c.setFont(base, 11)
                    c.drawCentredString(cx + 2 * mm, fy + 2.1 * mm, '/')
                    cx += 4 * mm
        else:
            textbox(key, lab, x, fy, w, h, multiline=(kind == 'big'))
        return LAB + h

    def row(fields, left=None, width=None):
        x0 = margin if left is None else left
        span_all = avail if width is None else width
        gap = 4 * mm
        wsum = sum(f[1] for f in fields)
        span = span_all - gap * (len(fields) - 1)
        tall = max((FH * 1.55 if (len(f) > 2 and f[2] == 'big') else FH) for f in fields) + LAB
        ensure(tall + GAP_Y)
        x, hmax = x0, 0
        for f in fields:
            w = span * (f[1] / wsum)
            hmax = max(hmax, cell(f, x, w))
            x += w + gap
        st['y'] -= hmax + GAP_Y

    new_page(first=True)

    # 1 · Applicant — three rows beside a passport-photo box of the same height.
    heading('Applicant', 1)
    box_w = 33 * mm
    rows_h = 3 * (LAB + FH) + 2 * GAP_Y
    bx, by = PW - margin - box_w, st['y'] - rows_h
    c.setStrokeColor(line if not bw else colors.HexColor('#444444')); c.setDash(2.5, 2); c.setLineWidth(0.8)
    c.roundRect(bx, by, box_w, rows_h, 2 * mm, stroke=1, fill=0)
    c.setDash()
    c.setFillColor(muted); c.setFont(boldf, 7.5)
    c.drawCentredString(bx + box_w / 2, by + rows_h / 2 + 2.5 * mm, 'PASSPORT')
    c.drawCentredString(bx + box_w / 2, by + rows_h / 2 - 1 * mm, 'PHOTOGRAPH')
    c.setFont(base, 7)
    c.drawCentredString(bx + box_w / 2, by + rows_h / 2 - 5 * mm, 'paste here')
    left_w = avail - box_w - 6 * mm
    row([('First name', 1), ('Surname', 1)], width=left_w)
    row([('Middle name', 1), ('Gender', 1, 'checks', ['Male', 'Female'])], width=left_w)
    row([('Date of birth', 1, 'date')], width=left_w)

    heading('Origin & Health', 2)
    row([('Country', 1), ('State of origin', 1), ('L.G.A. of origin', 1)])
    row([("Father's occupation", 1.25), ('Languages spoken at home', 1.25),
         ('Blood group', 0.6), ('Genotype', 0.6)])

    heading('Application', 3)
    row([('Class applying for', 0.9), ('Previous school', 1.4), ('How did you hear about us?', 1.1)])

    heading('Parent / Guardian', 4)
    row([('Full name', 1.4), ('Relationship', 0.75), ('Phone', 0.95), ('Email', 1.3)])
    row([('Residential address', 1, 'big')])

    heading('Emergency contact', 5)
    row([('Full name', 1.4), ('Relationship', 0.75), ('Phone', 1)])
    row([('Address', 1, 'big')])

    # Declaration + signatures
    ensure(26 * mm)
    st['y'] -= 1 * mm
    c.setFillColor(ink); c.setFont(obl, 8.3)
    c.drawString(margin, st['y'] - 3 * mm,
                 'I confirm that the information on this form is correct, and I agree to the school’s rules and fee terms.')
    sy = st['y'] - 10.5 * mm
    c.setStrokeColor(ink); c.setLineWidth(0.7)
    c.line(margin, sy, margin + 82 * mm, sy)
    c.line(PW - margin - 50 * mm, sy, PW - margin, sy)
    c.setFillColor(muted); c.setFont(boldf, 7.3)
    c.drawString(margin, sy - 3.6 * mm, 'PARENT / GUARDIAN SIGNATURE')
    c.drawString(PW - margin - 50 * mm, sy - 3.6 * mm, 'DATE')
    st['y'] = sy - 6 * mm

    # For office use only
    oh = 2 * LAB + 2 * FH + GAP_Y + 7.5 * mm
    if st['y'] - oh >= margin + 7.5 * mm:
        oy = st['y'] - oh
        c.setFillColor(office_bg); c.setStrokeColor(gold if not bw else colors.black); c.setLineWidth(0.8)
        c.setDash(3, 2) if bw else None
        c.roundRect(margin, oy, avail, oh, 2.5 * mm, stroke=1, fill=1)
        c.setDash()
        c.setFillColor(navy); c.setFont(boldf, 8.5)
        c.drawString(margin + 3.5 * mm, oy + oh - 4.2 * mm, 'FOR OFFICE USE ONLY')
        st['y'] = oy + oh - 6 * mm
        inner = avail - 7 * mm
        st['fixed'] = True
        row([('Application no.', 1), ('Date received', 1), ('Entrance score', 0.8)], left=margin + 3.5 * mm, width=inner)
        row([('Decision', 1.6, 'checks', ['Offered', 'Not offered', 'Waiting list']), ("Officer's name / signature", 1.2)],
            left=margin + 3.5 * mm, width=inner)
        st['fixed'] = False

    c.showPage(); c.save()
    return buf.getvalue()
