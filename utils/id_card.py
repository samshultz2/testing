"""Student ID card generator (Academic Documents & Publishing — bespoke types).

Produces a print-ready **CR80 portrait ID card** (front + back) laid out on a
single A4 page with cut outlines, so a school can print and guillotine it. The
card carries the school branding, the student's photo (or a placeholder), their
core identity details, a QR code that resolves to the public verification page,
and a Code128 barcode of the admission number for scanners.

Data is passed in already-resolved (class label, session, guardian) so this
module stays free of query logic and is trivially testable.
"""
import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas as _canvas

CARD_W = 54 * mm
CARD_H = 95 * mm


def _hex(v, fallback):
    v = (v or '').strip()
    return colors.HexColor(v) if v.startswith('#') and len(v) in (4, 7) else colors.HexColor(fallback)


def _esc(v):
    return str(v if v is not None else '')


def _photo(student):
    """Return an ImageReader for the student photo, or None to draw a placeholder.
    Prefers the stored passport photo (tenant DB); falls back to a filesystem
    ``photo_url``. Best-effort: a missing/broken image never breaks the card."""
    # Primary: the passport photo stored in the tenant DB.
    try:
        from utils import student_photo
        r = student_photo.photo_reader(student)
        if r is not None:
            return r
    except Exception:
        pass
    # Fallback: a local filesystem/static path in photo_url (legacy).
    path = getattr(student, 'photo_url', None) or ''
    if not path or path.startswith('data:'):
        return None
    try:
        import os
        from reportlab.lib.utils import ImageReader
        if 'static/' in path:
            fs = os.path.join('static', path.split('static/', 1)[1])
            return ImageReader(fs) if os.path.exists(fs) else None
        if path.startswith('/') or path.startswith('./'):
            return ImageReader(path) if os.path.exists(path) else None
    except Exception:
        return None
    return None


def _qr(value, size):
    try:
        import qrcode
        from reportlab.lib.utils import ImageReader
        img = qrcode.make(str(value or '0'))
        buf = io.BytesIO(); img.save(buf, 'PNG'); buf.seek(0)
        return ImageReader(buf)
    except Exception:
        return None


def _draw_barcode(c, value, x, y, width, height=7 * mm):
    try:
        from reportlab.graphics.barcode import code128
        bc = code128.Code128(str(value or '0'), barHeight=height, barWidth=0.28 * mm)
        bw = getattr(bc, 'width', 0) or width
        scale = min(1.0, width / bw) if bw else 1.0
        c.saveState()
        c.translate(x, y)
        c.scale(scale, 1)
        bc.drawOn(c, 0, 0)
        c.restoreState()
    except Exception:
        pass


def _front(c, x, y, ctx):
    """Draw the front of the card with its lower-left corner at (x, y). Laid out
    strictly top-down so blocks never overlap."""
    primary, accent, gold = ctx['primary'], ctx['accent'], ctx['gold']
    st = ctx['student']
    cx = x + CARD_W / 2
    # card body + cut outline
    c.setStrokeColor(colors.HexColor('#cbd5e1')); c.setLineWidth(0.5)
    c.setFillColor(colors.white)
    c.roundRect(x, y, CARD_W, CARD_H, 3 * mm, stroke=1, fill=1)
    # header band
    band_h = 18 * mm
    c.setFillColor(primary)
    c.rect(x, y + CARD_H - band_h, CARD_W, band_h, stroke=0, fill=1)
    logo = ctx.get('logo')
    if logo is not None:
        try:
            c.drawImage(logo, x + 3 * mm, y + CARD_H - 13 * mm, width=10 * mm, height=10 * mm,
                        mask='auto', preserveAspectRatio=True)
        except Exception:
            pass
    c.setFillColor(colors.white); c.setFont('Helvetica-Bold', 7)
    _wrapped_center(c, ctx['school_name'].upper(), cx + 4 * mm, y + CARD_H - 7 * mm, 33 * mm, 7)
    c.setFillColor(colors.HexColor('#e2e8f0')); c.setFont('Helvetica', 4.6)
    c.drawCentredString(cx, y + CARD_H - band_h + 2.4 * mm, 'STUDENT IDENTITY CARD')

    # photo (left) + QR (right)
    pw, ph = 22 * mm, 26 * mm
    top = y + CARD_H - band_h - 3 * mm
    px, py = x + 4 * mm, top - ph
    photo = _photo(st)
    c.setStrokeColor(gold); c.setLineWidth(1)
    if photo is not None:
        try:
            c.drawImage(photo, px, py, width=pw, height=ph, mask='auto', preserveAspectRatio=True)
            c.rect(px, py, pw, ph, stroke=1, fill=0)
        except Exception:
            photo = None
    if photo is None:
        c.setFillColor(colors.HexColor('#eef2f7')); c.rect(px, py, pw, ph, stroke=1, fill=1)
        c.setFillColor(colors.HexColor('#94a3b8')); c.setFont('Helvetica', 5)
        c.drawCentredString(px + pw / 2, py + ph / 2 - 1, 'PHOTOGRAPH')
    qr = _qr(ctx.get('verify') or st.student_id, 20 * mm)
    if qr is not None:
        try:
            c.drawImage(qr, x + CARD_W - 24 * mm, top - 20 * mm, width=20 * mm, height=20 * mm, mask='auto')
        except Exception:
            pass

    # name
    ny = py - 5 * mm
    c.setFillColor(primary); c.setFont('Helvetica-Bold', 8.5)
    _wrapped_center(c, st.full_name.upper(), cx, ny, CARD_W - 8 * mm, 8.5)
    c.setStrokeColor(colors.HexColor('#e2e8f0')); c.setLineWidth(0.5)
    c.line(x + 6 * mm, ny - 3 * mm, x + CARD_W - 6 * mm, ny - 3 * mm)

    # details (5 essential rows; blood group lives on the back)
    rows = [('ID No.', st.student_id), ('Class', ctx.get('class_label') or ''),
            ('Session', ctx.get('session') or ''), ('Sex', getattr(st, 'gender', '') or ''),
            ('D.O.B', ctx.get('dob') or '')]
    ry = ny - 7 * mm
    for lab, val in rows:
        if not val:
            continue
        c.setFillColor(colors.HexColor('#64748b')); c.setFont('Helvetica-Bold', 6)
        c.drawString(x + 5 * mm, ry, lab)
        c.setFillColor(colors.HexColor('#111827')); c.setFont('Helvetica', 6.4)
        c.drawString(x + 20 * mm, ry, _esc(val)[:24])
        ry -= 4.6 * mm

    # barcode + footer anchored at the foot (kept clear of the rows above)
    foot_h = 4 * mm
    _draw_barcode(c, st.student_id, x + 5 * mm, y + foot_h + 3 * mm, CARD_W - 10 * mm, height=6.5 * mm)
    c.setFillColor(colors.HexColor('#94a3b8')); c.setFont('Helvetica', 4.4)
    c.drawCentredString(cx, y + foot_h + 1 * mm, _esc(st.student_id))
    c.setFillColor(accent); c.rect(x, y, CARD_W, foot_h, stroke=0, fill=1)
    c.setFillColor(colors.white); c.setFont('Helvetica-Oblique', 4.6)
    c.drawCentredString(cx, y + 1.3 * mm,
                        (ctx.get('motto') or f"Valid for {ctx.get('session') or 'the session'}")[:52])


def _back(c, x, y, ctx):
    primary, accent = ctx['primary'], ctx['accent']
    c.setStrokeColor(colors.HexColor('#cbd5e1')); c.setLineWidth(0.5)
    c.setFillColor(colors.white)
    c.roundRect(x, y, CARD_W, CARD_H, 3 * mm, stroke=1, fill=1)
    c.setFillColor(primary)
    c.rect(x, y + CARD_H - 8 * mm, CARD_W, 8 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white); c.setFont('Helvetica-Bold', 6.5)
    c.drawCentredString(x + CARD_W / 2, y + CARD_H - 5.4 * mm, 'CARD HOLDER INFORMATION')
    ty = y + CARD_H - 13 * mm
    c.setFillColor(colors.HexColor('#111827'))

    def line(label, value, big=False):
        nonlocal ty
        if not value:
            return
        c.setFont('Helvetica-Bold', 5.6); c.setFillColor(colors.HexColor('#64748b'))
        c.drawString(x + 4 * mm, ty, label)
        ty -= 4 * mm
        c.setFont('Helvetica', 6.2); c.setFillColor(colors.HexColor('#111827'))
        for seg in _wrap(value, 42):
            c.drawString(x + 4 * mm, ty, seg); ty -= 3.6 * mm
        ty -= 1.5 * mm

    st = ctx['student']
    bg = getattr(st, 'blood_group', '') or ''
    gt = getattr(st, 'genotype', '') or ''
    if bg or gt:
        line('Blood Group / Genotype', ' / '.join([s for s in [bg, gt] if s]))
    line('Guardian / Next of Kin', ctx.get('guardian') or '')
    line('Guardian Phone', ctx.get('guardian_phone') or '')
    line('Home Address', ctx.get('address') or '')
    # terms
    ty = min(ty, y + 30 * mm)
    c.setFont('Helvetica-Oblique', 4.8); c.setFillColor(colors.HexColor('#475569'))
    terms = ("This card is the property of the school and must be surrendered on "
             "demand or on leaving. If found, please return to the address below.")
    for seg in _wrap(terms, 52):
        c.drawString(x + 4 * mm, ty, seg); ty -= 3.2 * mm
    # return-to strip
    c.setFillColor(accent); c.rect(x, y, CARD_W, 9 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white); c.setFont('Helvetica-Bold', 4.8)
    c.drawCentredString(x + CARD_W / 2, y + 5.4 * mm, ctx['school_name'][:46])
    c.setFont('Helvetica', 4.4)
    c.drawCentredString(x + CARD_W / 2, y + 2.2 * mm,
                        ' · '.join([s for s in [ctx.get('address'), ctx.get('school_phone')] if s])[:56])


def _wrap(text, width):
    words, lines, cur = _esc(text).split(), [], ''
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = (cur + ' ' + w).strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or ['']


def _wrapped_center(c, text, cx, top, width, size):
    """Draw centered text, wrapping to at most 2 lines within ``width`` (pt-agnostic
    heuristic on character count)."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    font = c._fontname
    if stringWidth(text, font, size) <= width:
        c.drawCentredString(cx, top, text)
        return
    words, line1, line2, filling_first = text.split(), '', '', True
    for w in words:
        if filling_first:
            trial = (line1 + ' ' + w).strip()
            if not line1 or stringWidth(trial, font, size) <= width:
                line1 = trial
                continue
            filling_first = False          # once line 1 is full, keep word order
        line2 = (line2 + ' ' + w).strip()
    c.drawCentredString(cx, top + size * 0.5, line1)
    if line2:
        c.drawCentredString(cx, top - size * 0.55, line2[:40])


def render_id_card(student, *, school=None, class_label='', session='', dob='',
                   guardian='', guardian_phone='', address='', verify_url=None,
                   branding=None):
    """Return a BytesIO PDF: an A4 sheet holding the front & back CR80 cards with
    cut outlines."""
    school = school or {}
    branding = branding or {}
    ctx = {
        'student': student,
        'school_name': school.get('name') or 'School',
        'school_phone': school.get('phone') or '',
        'address': address or school.get('address') or '',
        'motto': school.get('motto') or '',
        'class_label': class_label, 'session': session, 'dob': dob,
        'guardian': guardian, 'guardian_phone': guardian_phone,
        'verify': verify_url,
        'primary': _hex(branding.get('doc_primary_color'), '#0e3a2f'),
        'accent': _hex(branding.get('doc_accent_color'), '#0e8a64'),
        'gold': _hex(branding.get('doc_secondary_color'), '#b7791f'),
    }
    ctx['logo'] = None
    try:
        import os
        from reportlab.lib.utils import ImageReader
        from utils.school import logo_path
        p = logo_path()
        if p and os.path.exists(p):
            ctx['logo'] = ImageReader(p)
    except Exception:
        ctx['logo'] = None

    buf = io.BytesIO()
    c = _canvas.Canvas(buf, pagesize=A4)
    pw, ph = A4
    gap = 12 * mm
    total_w = CARD_W * 2 + gap
    x0 = (pw - total_w) / 2
    y0 = (ph - CARD_H) / 2 + 6 * mm
    # cut guide caption
    c.setFillColor(colors.HexColor('#94a3b8')); c.setFont('Helvetica', 8)
    c.drawCentredString(pw / 2, y0 + CARD_H + 10 * mm, 'Student ID Card — front (left) & back (right). Cut along the outlines.')
    _front(c, x0, y0, ctx)
    _back(c, x0 + CARD_W + gap, y0, ctx)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


# --- whole-class sheets -----------------------------------------------------

_GRID_COLS = 3
_GRID_ROWS = 2
_GRID_GAP_X = 6 * mm
_GRID_GAP_Y = 9 * mm


def _shared_ctx(school, branding):
    """The per-sheet context (branding, colours, logo) shared by every card."""
    school = school or {}
    branding = branding or {}
    ctx = {
        'school_name': school.get('name') or 'School',
        'school_phone': school.get('phone') or '',
        'motto': school.get('motto') or '',
        'default_address': school.get('address') or '',
        'primary': _hex(branding.get('doc_primary_color'), '#0e3a2f'),
        'accent': _hex(branding.get('doc_accent_color'), '#0e8a64'),
        'gold': _hex(branding.get('doc_secondary_color'), '#b7791f'),
        'logo': None,
    }
    try:
        import os
        from reportlab.lib.utils import ImageReader
        from utils.school import logo_path
        p = logo_path()
        if p and os.path.exists(p):
            ctx['logo'] = ImageReader(p)
    except Exception:
        ctx['logo'] = None
    return ctx


def _card_ctx(base, card):
    """Merge a per-student ``card`` dict onto the shared ``base`` context."""
    ctx = dict(base)
    ctx['student'] = card['student']
    ctx['class_label'] = card.get('class_label') or ''
    ctx['session'] = card.get('session') or ''
    ctx['dob'] = card.get('dob') or ''
    ctx['guardian'] = card.get('guardian') or ''
    ctx['guardian_phone'] = card.get('guardian_phone') or ''
    ctx['address'] = card.get('address') or base.get('default_address') or ''
    ctx['verify'] = card.get('verify')
    return ctx


def _grid_positions(pw, ph):
    """Lower-left (x, y) of each of the up-to-6 card slots on an A4 page, in
    reading order (row-major, top-left first)."""
    grid_w = _GRID_COLS * CARD_W + (_GRID_COLS - 1) * _GRID_GAP_X
    x_left = (pw - grid_w) / 2
    top = ph - 18 * mm                       # first row's top edge (room for caption)
    pos = []
    for r in range(_GRID_ROWS):
        row_top = top - r * (CARD_H + _GRID_GAP_Y)
        for col in range(_GRID_COLS):
            pos.append((x_left + col * (CARD_W + _GRID_GAP_X), row_top - CARD_H))
    return pos


def render_class_id_cards(cards, *, school=None, branding=None, include_backs=True,
                          title=''):
    """Return a BytesIO PDF laying out a whole class's ID cards, 6 per A4 page.

    ``cards`` is a list of per-student dicts ({'student': s, 'class_label': ...,
    'session', 'dob', 'guardian', 'guardian_phone', 'address', 'verify'}). Fronts
    are printed first (all pages), then — if ``include_backs`` — the backs in the
    **same order and slot positions**, so a school can print both, cut, and mount
    each back behind its front. Cut outlines are drawn on every card."""
    base = _shared_ctx(school, branding)
    buf = io.BytesIO()
    c = _canvas.Canvas(buf, pagesize=A4)
    pw, ph = A4
    positions = _grid_positions(pw, ph)
    per_page = len(positions)
    ctxs = [_card_ctx(base, card) for card in cards]

    def caption(text):
        c.setFillColor(colors.HexColor('#94a3b8')); c.setFont('Helvetica', 8)
        c.drawCentredString(pw / 2, ph - 12 * mm, text)

    def paint(face_fn, label):
        for start in range(0, len(ctxs), per_page):
            page = ctxs[start:start + per_page]
            caption(label)
            for ctx, (x, y) in zip(page, positions):
                face_fn(c, x, y, ctx)
            c.showPage()

    heading = (title + ' — ') if title else ''
    if ctxs:
        paint(_front, heading + 'ID cards (fronts). Cut along the outlines.')
        if include_backs:
            paint(_back, heading + 'ID cards (backs) — same order as the fronts.')
    else:
        caption('No students to print.')
        c.showPage()
    c.save()
    buf.seek(0)
    return buf
