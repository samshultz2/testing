"""Server-side PDF of a fee-payment receipt (reportlab).

Mirrors templates/finance/receipt.html so the downloaded file matches the
on-screen receipt — reliable on any device (window.print() is flaky on mobile).
"""
import io

from reportlab.lib.pagesizes import A5
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from utils.web_exports import pdf_escape
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                Spacer, HRFlowable)

_PRIMARY = colors.HexColor('#0e8a64')
_FONTS = __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), '..', 'assets', 'fonts')


def _fonts():
    """(regular, bold) font names with a ₦ glyph. The PDF built-in Helvetica
    has no ₦, so viewers drew an empty box where the currency sign should be.
    Inter ships with the app; DejaVu / Liberation are fallbacks."""
    import os
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if 'Rcp' in pdfmetrics.getRegisteredFontNames():
        return 'Rcp', 'Rcp-Bold'
    for reg, bold in ((os.path.join(_FONTS, 'Inter-Regular.ttf'), os.path.join(_FONTS, 'Inter-Bold.ttf')),
                      ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
                      ('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
                       '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf')):
        if os.path.exists(reg) and os.path.exists(bold):
            try:
                pdfmetrics.registerFont(TTFont('Rcp', reg))
                pdfmetrics.registerFont(TTFont('Rcp-Bold', bold))
                pdfmetrics.registerFontFamily('Rcp', normal='Rcp', bold='Rcp-Bold', italic='Rcp', boldItalic='Rcp-Bold')
                return 'Rcp', 'Rcp-Bold'
            except Exception:
                continue
    return 'Helvetica', 'Helvetica-Bold'
_MUTED = colors.HexColor('#64748b')


_SIGN = {'v': '₦'}


def _naira(v):
    try:
        return _SIGN['v'] + '{:,.2f}'.format(float(v or 0))
    except (TypeError, ValueError):
        return _SIGN['v'] + '0.00'


def receipt_pdf(payment, bill, school):
    """Return (BytesIO, filename) for a payment receipt."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A5,
                            leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f'Receipt {payment.receipt_no}')
    ss = getSampleStyleSheet()
    body, _bold = _fonts()
    _SIGN['v'] = 'N' if body == 'Helvetica' else '₦'      # no ₦ glyph -> plain N, never a box
    base = ParagraphStyle('base', parent=ss['Normal'], fontName=body)
    center = ParagraphStyle('c', parent=base, alignment=TA_CENTER)
    title = ParagraphStyle('t', parent=center, fontSize=15, leading=18,
                           textColor=_PRIMARY, spaceAfter=2)
    muted = ParagraphStyle('m', parent=center, fontSize=8, textColor=_MUTED)
    label = ParagraphStyle('l', parent=center, fontSize=8, textColor=_MUTED,
                           spaceAfter=1)
    big = ParagraphStyle('b', parent=center, fontSize=20, leading=22,
                         textColor=_PRIMARY)

    el = []
    nm = school.get('name') or 'School'
    items = [(Paragraph(pdf_escape(nm), title), nm, body, 15)]
    br = getattr(payment.student, 'branch', None) if payment.student else None
    if br:
        items.append((Paragraph(pdf_escape(f'{br.name} Branch'), muted), f'{br.name} Branch', body, 8))
    if school.get('address'):
        items.append((Paragraph(pdf_escape(school['address']), muted), school['address'], body, 8))
    if school.get('phone'):
        items.append((Paragraph(pdf_escape(school['phone']), muted), school['phone'], body, 8))
    from utils.school import logo_flowable, logo_header_flowable
    logo = logo_flowable(max_h_mm=14, max_w_mm=22)
    header = logo_header_flowable(logo, items) if logo is not None else None
    if header is not None:
        el.append(header)
    else:
        el.extend(it[0] for it in items)
    el.append(Spacer(1, 4))
    el.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#cbd5e1'),
                         dash=(2, 2)))
    el.append(Spacer(1, 4))
    el.append(Paragraph('<b>FEE PAYMENT RECEIPT</b>', center))
    el.append(Spacer(1, 6))

    def row(k, v, strong=False):
        vv = f'<b>{pdf_escape(v)}</b>' if strong else pdf_escape(v)
        return [Paragraph(k, label), Paragraph(vv, ParagraphStyle(
            'r', parent=base, fontSize=9, alignment=2))]

    rows = [
        row('Receipt No.', payment.receipt_no, True),
        row('Date', payment.payment_date.strftime('%d %B %Y') if payment.payment_date else ''),
        row('Student', payment.student.full_name if payment.student else ''),
        row('Student ID', payment.student.student_id if payment.student else ''),
        row('Term', payment.term.full_name if payment.term else ''),
        row('Method', payment.method + (f' · {payment.reference}' if payment.reference else '')),
    ]
    t = Table(rows, colWidths=[40 * mm, None])
    t.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -2), 0.4, colors.HexColor('#eef2f7')),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    el.append(t)
    el.append(Spacer(1, 8))

    amt = Table([[Paragraph('Amount Paid', label)], [Paragraph(_naira(payment.amount), big)]],
                colWidths=[None])
    amt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e6f7ef')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    el.append(amt)
    el.append(Spacer(1, 8))

    items = list(getattr(payment, 'items', None) or [])
    if items:
        el.append(Paragraph('Paid for', label))
        prow = [row(it.fee_item.name if it.fee_item else 'Fee item', _naira(it.amount)) for it in items]
        rest = (payment.amount or 0) - sum(it.amount for it in items)
        if rest > 0.005:
            prow.append(row('Toward the rest of the bill', _naira(rest)))
        pt = Table(prow, colWidths=[None, 40 * mm])
        pt.setStyle(TableStyle([
            ('LINEBELOW', (0, 0), (-1, -2), 0.4, colors.HexColor('#eef2f7')),
            ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ]))
        el.append(pt)
        el.append(Spacer(1, 8))

    summ = [
        row('Total billed (term)', _naira(bill.get('billed'))),
    ]
    if bill.get('discount'):
        summ.append(row('Discount / waiver', '− ' + _naira(bill['discount'])))
    summ.append(row('Total paid to date', _naira(bill.get('paid'))))
    summ.append(row('Outstanding balance', _naira(bill.get('balance')), True))
    st = Table(summ, colWidths=[40 * mm, None])
    st.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -2), 0.4, colors.HexColor('#eef2f7')),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    el.append(st)
    el.append(Spacer(1, 12))
    el.append(Paragraph(f'Received by: {pdf_escape(payment.received_by) or "__________"}', muted))

    doc.build(el)
    buf.seek(0)
    return buf, f'receipt-{payment.receipt_no}.pdf'
