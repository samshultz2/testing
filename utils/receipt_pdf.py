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
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                Spacer, HRFlowable)

_PRIMARY = colors.HexColor('#0e8a64')
_MUTED = colors.HexColor('#64748b')


def _naira(v):
    try:
        return '₦{:,.2f}'.format(float(v or 0))
    except (TypeError, ValueError):
        return '₦0.00'


def receipt_pdf(payment, bill, school):
    """Return (BytesIO, filename) for a payment receipt."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A5,
                            leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f'Receipt {payment.receipt_no}')
    ss = getSampleStyleSheet()
    center = ParagraphStyle('c', parent=ss['Normal'], alignment=TA_CENTER)
    title = ParagraphStyle('t', parent=center, fontSize=15, leading=18,
                           textColor=_PRIMARY, spaceAfter=2)
    muted = ParagraphStyle('m', parent=center, fontSize=8, textColor=_MUTED)
    label = ParagraphStyle('l', parent=center, fontSize=8, textColor=_MUTED,
                           spaceAfter=1)
    big = ParagraphStyle('b', parent=center, fontSize=20, leading=22,
                         textColor=_PRIMARY)

    el = []
    nm = school.get('name') or 'School'
    items = [(Paragraph(nm, title), nm, 'Helvetica', 15)]
    br = getattr(payment.student, 'branch', None) if payment.student else None
    if br:
        items.append((Paragraph(f'{br.name} Branch', muted), f'{br.name} Branch', 'Helvetica', 8))
    if school.get('address'):
        items.append((Paragraph(school['address'], muted), school['address'], 'Helvetica', 8))
    if school.get('phone'):
        items.append((Paragraph(school['phone'], muted), school['phone'], 'Helvetica', 8))
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
        vv = f'<b>{v}</b>' if strong else v
        return [Paragraph(k, label), Paragraph(vv, ParagraphStyle(
            'r', parent=ss['Normal'], fontSize=9, alignment=2))]

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
    el.append(Paragraph(f'Received by: {payment.received_by or "__________"}', muted))

    doc.build(el)
    buf.seek(0)
    return buf, f'receipt-{payment.receipt_no}.pdf'
