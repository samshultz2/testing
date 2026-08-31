"""Public verification receipt (Academic Documents & Publishing).

When a third party (an employer, a university) verifies a graduate document on the
public ``/verify`` portal, they can download a one-page A4 **verification receipt**
proving they carried out the check: the school branding, the confirmed document
summary, a tamper-evidence line, the exact time of the check, and a QR code back
to the live verification page. It carries only the same minimum details already
shown on the page — no extra PII.
"""
import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas as _canvas


def _hex(v, fallback):
    v = (v or '').strip()
    return colors.HexColor(v) if v.startswith('#') and len(v) in (4, 7) else colors.HexColor(fallback)


def _qr(value):
    try:
        import qrcode
        from reportlab.lib.utils import ImageReader
        img = qrcode.make(str(value or ''))
        buf = io.BytesIO(); img.save(buf, 'PNG'); buf.seek(0)
        return ImageReader(buf)
    except Exception:
        return None


def _logo(school):
    try:
        import os
        from reportlab.lib.utils import ImageReader
        p = (school or {}).get('logo_path')
        if p and os.path.exists(p):
            return ImageReader(p)
    except Exception:
        pass
    return None


def render_receipt(*, school=None, branding=None, result=None, code='',
                   verify_url='', checked_at=''):
    """Return a BytesIO A4 PDF receipt for one confirmed verification."""
    school = school or {}
    branding = branding or {}
    result = result or {}
    primary = _hex(branding.get('doc_primary_color'), '#0e3a2f')
    accent = _hex(branding.get('doc_accent_color'), '#0e8a64')

    buf = io.BytesIO()
    c = _canvas.Canvas(buf, pagesize=A4)
    pw, ph = A4
    mx = 22 * mm
    cx = pw / 2

    # top brand band
    band_h = 30 * mm
    c.setFillColor(primary)
    c.rect(0, ph - band_h, pw, band_h, stroke=0, fill=1)
    logo = _logo(school)
    if logo is not None:
        try:
            c.drawImage(logo, mx, ph - band_h + 6 * mm, width=18 * mm, height=18 * mm,
                        mask='auto', preserveAspectRatio=True)
        except Exception:
            pass
    c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold', 15)
    c.drawString(mx + 22 * mm, ph - 15 * mm, (school.get('name') or 'School')[:52])
    c.setFont('Helvetica', 9)
    c.setFillColor(colors.HexColor('#dbeae4'))
    c.drawString(mx + 22 * mm, ph - 21 * mm, 'Document Verification Receipt')

    y = ph - band_h - 16 * mm

    # genuine badge
    c.setFillColor(accent)
    c.circle(cx, y - 2 * mm, 8 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white); c.setFont('Helvetica-Bold', 12)
    c.drawCentredString(cx, y - 4.4 * mm, '✓')
    c.setFillColor(primary); c.setFont('Helvetica-Bold', 16)
    c.drawCentredString(cx, y - 20 * mm, 'GENUINE DOCUMENT')
    c.setFillColor(colors.HexColor('#4b5563')); c.setFont('Helvetica', 10)
    c.drawCentredString(cx, y - 26 * mm,
                        'The document below was confirmed as issued by this school.')

    # details table
    ty = y - 40 * mm
    rows = [
        ('Graduate', result.get('name')),
        ('Document', result.get('doc_label')),
        ('Document No.', result.get('number')),
        ('Class of', result.get('graduation')),
        ('Issued', result.get('issued')),
        ('Verification code', code),
    ]
    if result.get('reprint'):
        rows.append(('Copy', 'Reprint #%s' % result.get('reprint')))
    for lab, val in rows:
        if not val:
            continue
        c.setStrokeColor(colors.HexColor('#e5e7eb')); c.setLineWidth(0.5)
        c.line(mx, ty - 2 * mm, pw - mx, ty - 2 * mm)
        c.setFillColor(colors.HexColor('#6b7280')); c.setFont('Helvetica', 10)
        c.drawString(mx, ty, lab)
        c.setFillColor(colors.HexColor('#111827')); c.setFont('Helvetica-Bold', 10.5)
        c.drawRightString(pw - mx, ty, str(val)[:60])
        ty -= 9 * mm

    # trust + timestamp block
    ty -= 4 * mm
    if result.get('verify_count'):
        c.setFillColor(colors.HexColor('#374151')); c.setFont('Helvetica', 9.5)
        note = 'Independently verified %s time(s)' % result.get('verify_count')
        if result.get('first_checked'):
            note += ' · first checked %s' % result.get('first_checked')
        c.drawString(mx, ty, note); ty -= 7 * mm
    c.setFillColor(colors.HexColor('#374151')); c.setFont('Helvetica-Bold', 9.5)
    c.drawString(mx, ty, 'This check performed: %s' % (checked_at or ''))

    # QR to the live page
    qr = _qr(verify_url)
    if qr is not None:
        try:
            c.drawImage(qr, pw - mx - 30 * mm, 30 * mm, width=30 * mm, height=30 * mm, mask='auto')
        except Exception:
            pass
    c.setFillColor(colors.HexColor('#6b7280')); c.setFont('Helvetica', 8)
    c.drawString(mx, 42 * mm, 'Scan or visit to re-verify at any time:')
    c.setFillColor(accent); c.setFont('Helvetica', 8)
    c.drawString(mx, 37 * mm, (verify_url or '')[:70])

    # footer disclaimer
    c.setFillColor(colors.HexColor('#9ca3af')); c.setFont('Helvetica', 7.5)
    c.drawCentredString(cx, 16 * mm,
                        'This receipt reflects the verification result at the time shown above and may change if the school later revokes the document.')
    c.drawCentredString(cx, 12 * mm, 'Powered by EduSyncra · Document Verification Portal')
    c.showPage()
    c.save()
    buf.seek(0)
    return buf
