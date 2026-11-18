"""The "Profile" Mock WAEC result slip — a third theme beside Classic and
Modern (see utils.mock_slip_modern for the shared helpers).

The top of the page is a student profile card: passport photo (or initials),
name, class / stream / gender chips, the average as a ring chart, four stat
tiles and the core-subject status line. Below it the subject table with soft
alternating row tints and grade pills, the grading key, signatures, stamp and
footer. Every block can be switched off (PROFILE_OPTIONS).
"""
import io
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont

from utils.mock_slip_modern import (CORE, KEY, REMARK, _band, _fit, _on, _signed, _spaced,
                                    _wrap, competence_title)

_FONTS = os.path.join(os.path.dirname(__file__), '..', 'assets', 'fonts')

PROFILE_OPTIONS = [
    ('logo', 'School logo'), ('address', 'School address'), ('contact', 'Phone / email'),
    ('motto', 'School motto'),
    ('p_pill', '“RESULT SLIP” badge'), ('p_session', 'Session'),
    ('p_photo', 'Passport photo (initials when there is none)'),
    ('p_exam', 'Exam name & date'),
    ('p_class', 'Class'), ('p_stream', 'Stream'), ('p_gender', 'Gender'),
    ('p_ring', 'Average ring chart'),
    ('p_subjects', 'Tile — subjects sat'), ('p_credits', 'Tile — credits'),
    ('p_distinctions', 'Tile — distinctions'), ('p_avgtile', 'Tile — average vs previous mock'),
    ('p_change', 'Change since the previous mock'),
    ('p_five', '5 credits incl. English & Maths (Yes / No)'), ('p_missing', 'Missing core subjects'),
    ('p_core', '“CORE” tag on English & Maths'),
    ('score', 'Score column'), ('grade', 'Grade column'), ('remark', 'Remark column'),
    ('grades', 'Grading key'), ('p_stamp', 'Stamp circle'),
    ('p_footer', 'Footer note'), ('printed_on', 'Issued date'),
]
PROFILE_FLAGS = tuple(p for p, _ in PROFILE_OPTIONS)

INK = colors.HexColor('#151826')
BODY = colors.HexColor('#3A3F55')
MUTED = colors.HexColor('#6A7086')
FAINT = colors.HexColor('#8A90A6')
LINE = colors.HexColor('#DCE0EC')
CARD = colors.HexColor('#F3F5FC')
CARD_LINE = colors.HexColor('#E3E7F4')
ZEBRA = colors.HexColor('#F7F8FC')
TRACK = colors.HexColor('#E1E5F2')
ACCENT = colors.HexColor('#2E43A0')
CORE_BG = colors.HexColor('#E8ECFA')
GOOD = colors.HexColor('#136043')
WARN = colors.HexColor('#7A4C00')
BAD = colors.HexColor('#A3261A')

PILLS = {
    'd': (colors.HexColor('#E3F2EA'), colors.HexColor('#136043')),
    'c': (colors.HexColor('#E8ECFA'), colors.HexColor('#2E43A0')),
    'p': (colors.HexColor('#FCEFD9'), colors.HexColor('#7A4C00')),
    'f': (colors.HexColor('#FCE4E1'), colors.HexColor('#A3261A')),
    'a': (colors.HexColor('#EEF0F5'), colors.HexColor('#8A90A6')),
}
PILLS_BW = {
    'd': (colors.HexColor('#D9D9D9'), colors.black), 'c': (colors.HexColor('#EDEDED'), colors.black),
    'p': (colors.white, colors.black), 'f': (colors.white, colors.black),
    'a': (colors.white, colors.HexColor('#666666')),
}


def _fonts():
    """{'r','sb','b'}: DM Sans, else Helvetica."""
    if 'PfDM' in pdfmetrics.getRegisteredFontNames():
        return {'r': 'PfDM', 'sb': 'PfDM-SB', 'b': 'PfDM-B'}
    try:
        for name, f in (('PfDM', 'DMSans-Regular.ttf'), ('PfDM-SB', 'DMSans-SemiBold.ttf'),
                        ('PfDM-B', 'DMSans-Bold.ttf')):
            pdfmetrics.registerFont(TTFont(name, os.path.join(_FONTS, f)))
        return {'r': 'PfDM', 'sb': 'PfDM-SB', 'b': 'PfDM-B'}
    except Exception:
        return {'r': 'Helvetica', 'sb': 'Helvetica-Bold', 'b': 'Helvetica-Bold'}


def _photo_reader(student):
    """ImageReader for the student's passport photo, or None."""
    from reportlab.lib.utils import ImageReader
    try:
        ph = getattr(student, 'photo', None)
        if ph is not None and ph.data:
            return ImageReader(io.BytesIO(ph.data))
    except Exception:
        pass
    url = getattr(student, 'photo_url', None)
    if url and '/static/' in url:
        try:
            from flask import current_app
            p = os.path.join(current_app.root_path, 'static', url.split('?', 1)[0].split('/static/', 1)[1])
            if os.path.exists(p):
                return ImageReader(p)
        except Exception:
            pass
    return None


def _initials(student):
    parts = [p for p in ((student.surname or ''), (student.first_name or '')) if p]
    return ''.join(p[0] for p in parts[:2]).upper() or '?'


def draw_profile_slip(c, student, summary, exam, school, opts=None, signers='both', bw=False,
                      klass='', prev=None, prev_stats=None, issued=None):
    """Draw one A4 Profile slip on canvas ``c`` (caller calls showPage)."""
    F = _fonts()
    PW, PH = A4
    L, R = 34.5, PW - 34.5
    W = R - L
    accent = colors.black if bw else ACCENT
    pills = PILLS_BW if bw else PILLS
    good, warn, bad = (INK, INK, INK) if bw else (GOOD, WARN, BAD)
    card_fill = colors.white if bw else CARD
    zebra = colors.HexColor('#F2F2F2') if bw else ZEBRA
    school = school or {}
    sname = school.get('name') or 'School'

    # ---- header -------------------------------------------------------------------
    y = PH - 28.5
    x = L
    logo = school.get('logo_path') if _on(opts, 'logo') else None
    if logo and os.path.exists(logo):
        try:
            from reportlab.lib.utils import ImageReader
            ir = ImageReader(logo)
            c.drawImage(ir, L, y - 39, width=39, height=39, mask='auto', preserveAspectRatio=True)
            x = L + 39 + 10.5
        except Exception:
            x = L
    right_w = 0
    if _on(opts, 'p_pill') or (_on(opts, 'p_session') and exam.session):
        right_w = 92
    avail = R - right_w - x - 8
    c.setFillColor(INK)
    nsize = _fit(sname, F['b'], 13.5, avail, 9)
    c.setFont(F['b'], nsize)
    c.drawString(x, y - 15, sname)
    bits = []
    if _on(opts, 'address') and school.get('address'):
        bits.append(school['address'])
    if _on(opts, 'contact'):
        bits += [b for b in (school.get('phone'), school.get('email')) if b]
    ly = y - 27
    if bits:
        line = ' · '.join(bits)
        c.setFont(F['r'], _fit(line, F['r'], 7.9, avail, 6.4))
        c.setFillColor(MUTED)
        c.drawString(x, ly, line)
        ly -= 10.5
    motto = (school.get('motto') or '').strip() if _on(opts, 'motto') else ''
    if motto:
        c.setFont(F['r'], _fit(motto, F['r'], 7.5, avail, 6.2))
        c.setFillColor(FAINT)
        c.drawString(x, ly, motto)
    if _on(opts, 'p_pill'):
        label = 'RESULT SLIP'
        tw = stringWidth(label, F['b'], 7.5) + 1.1 * (len(label) - 1)
        pw, ph = tw + 16, 16.5
        c.setFillColor(accent)
        c.roundRect(R - pw, y - 20, pw, ph, ph / 2, stroke=0, fill=1)
        _spaced(c, R - pw + 8, y - 14.5, label, F['b'], 7.5, colors.white, 1.1)
    if _on(opts, 'p_session') and exam.session:
        c.setFont(F['r'], 7.9)
        c.setFillColor(MUTED)
        c.drawRightString(R, y - 33, f'{exam.session.name} session')
    y -= 39 + 16.5

    # ---- the numbers --------------------------------------------------------------------
    res = list(summary.get('results') or [])
    n_all = len(res)
    absent = sum(1 for r in res if getattr(r, 'is_absent', False))
    credits = summary.get('credits') or 0
    avg = summary.get('average_score')
    has_prev = prev is not None and prev_stats is not None and _on(opts, 'p_change')
    prev_name = competence_title(prev) if prev is not None else ''
    prev_short = prev_name.split(' ')[0] if prev_name else ''
    missing = list(summary.get('missing_core') or [])

    tiles = []
    if _on(opts, 'p_subjects'):
        tiles.append(('Subjects sat', str(n_all - absent), f' / {n_all}',
                      (f'{absent} paper{"s" if absent != 1 else ""} missed', warn) if absent else ('All papers sat', FAINT)))
    if _on(opts, 'p_credits'):
        sub = ('A1 to C6', FAINT)
        if has_prev:
            d = credits - (prev_stats[0] or 0)
            sub = (f'{_signed(d)} since {prev_short}', good if d > 0 else (bad if d < 0 else FAINT))
        tiles.append(('Credits', str(credits), '', sub))
    if _on(opts, 'p_distinctions'):
        tiles.append(('Distinctions', str(summary.get('distinctions') or 0), '', ('A1, B2 or B3', FAINT)))
    if _on(opts, 'p_avgtile'):
        if has_prev and avg is not None and prev_stats[1] is not None:
            d = round(avg - prev_stats[1], 1)
            tiles.append((f'Average vs {prev_short}', _signed(d), ' pts',
                          (f'{prev_stats[1]:.1f}% → {avg:.1f}%', good if d > 0 else (bad if d < 0 else FAINT))))
        elif not _on(opts, 'p_ring'):
            tiles.append(('Average', f'{avg:.1f}' if avg is not None else '—', '%' if avg is not None else '', None))
    status = []
    if _on(opts, 'p_five'):
        ok = bool(summary.get('has_5_incl_core'))
        status.append(('5 credits incl. English & Maths:', 'Yes' if ok else 'No', good if ok else bad))
    if _on(opts, 'p_missing'):
        status.append(('Missing core:', ', '.join(missing) if missing else 'None', bad if missing else good))

    # ---- profile card: lay out first, then paint the panel behind it ---------------------
    show_photo, show_ring = _on(opts, 'p_photo'), _on(opts, 'p_ring') and avg is not None
    pad = 18
    photo_w, photo_h = 69, 84
    ring_d = 84
    tx = L + pad + (photo_w + 15 if show_photo else 0)
    tw = R - pad - (ring_d + 12 if show_ring else 0) - tx
    full = student.full_name or ''
    nsize = _fit(full, F['b'], 19.5, tw, 15)
    lines = _wrap(full, F['b'], nsize, tw)[:2]
    chips = []
    if _on(opts, 'p_class') and klass:
        chips.append(('Class', klass))
    if _on(opts, 'p_stream') and getattr(student, 'stream', None):
        chips.append(('Stream', student.stream))
    if _on(opts, 'p_gender') and student.gender:
        chips.append(('Gender', student.gender))
    text_h = (13 if _on(opts, 'p_exam') else 0) + len(lines) * nsize * 1.12 + (24 if chips else 0)
    top_h = max(text_h, photo_h if show_photo else 0, ring_d if show_ring else 0)
    tile_h = 57 if tiles else 0
    status_h = 16 if status else 0
    card_h = pad + top_h + (13.5 + tile_h if tiles else 0) + (12 + status_h if status else 0) + pad
    card_top = y
    c.setFillColor(card_fill)
    c.setStrokeColor(LINE if bw else CARD_LINE)
    c.setLineWidth(0.75)
    c.roundRect(L, card_top - card_h, W, card_h, 16.5, stroke=1, fill=1)

    row_top = card_top - pad
    mid = row_top - top_h / 2
    if show_photo:
        px, py = L + pad, mid - photo_h / 2
        ir = _photo_reader(student)
        c.setFillColor(colors.white)
        c.setStrokeColor(LINE)
        c.roundRect(px, py, photo_w, photo_h, 10.5, stroke=1, fill=1)
        if ir is not None:
            try:
                c.saveState()
                p = c.beginPath()
                p.roundRect(px, py, photo_w, photo_h, 10.5)
                c.clipPath(p, stroke=0, fill=0)
                c.drawImage(ir, px, py, photo_w, photo_h, preserveAspectRatio=True, anchor='c', mask='auto')
                c.restoreState()
            except Exception:
                c.restoreState()
        else:
            ini = _initials(student)
            c.setFont(F['b'], 22)
            c.setFillColor(LINE if not bw else colors.HexColor('#BBBBBB'))
            c.drawCentredString(px + photo_w / 2, py + photo_h / 2 - 8, ini)
    ty = mid + text_h / 2
    if _on(opts, 'p_exam'):
        bits = [competence_title(exam).upper()]
        if exam.exam_date:
            bits.append((exam.date_label() if hasattr(exam, 'date_label') else exam.exam_date.strftime('%d %b %Y')).upper())
        label = ' · '.join(bits)
        _spaced(c, tx, ty - 7, label[:60], F['b'], 8.25, accent, 0.9)
        ty -= 13
    c.setFont(F['b'], nsize)
    c.setFillColor(INK)
    for ln in lines:
        c.drawString(tx, ty - nsize * 0.9, ln)
        ty -= nsize * 1.12
    if chips:
        ty -= 6
        cx = tx
        for k, v in chips:
            w = stringWidth(k + ' ', F['r'], 8.25) + stringWidth(v, F['b'], 8.25) + 15
            if cx + w > tx + tw:
                break
            c.setFillColor(colors.white)
            c.setStrokeColor(LINE)
            c.roundRect(cx, ty - 16.5, w, 16.5, 8.25, stroke=1, fill=1)
            c.setFont(F['r'], 8.25)
            c.setFillColor(FAINT)
            c.drawString(cx + 7.5, ty - 11.2, k + ' ')
            c.setFont(F['b'], 8.25)
            c.setFillColor(INK)
            c.drawString(cx + 7.5 + stringWidth(k + ' ', F['r'], 8.25), ty - 11.2, v)
            cx += w + 4.5
    if show_ring:
        rcx, rcy = R - pad - ring_d / 2, mid
        r = ring_d / 2 - 3.5
        c.setLineWidth(6.75)
        c.setStrokeColor(TRACK if not bw else colors.HexColor('#DDDDDD'))
        c.setFillColor(colors.white)
        c.circle(rcx, rcy, r, stroke=1, fill=1)
        pct = max(0.0, min(100.0, avg)) / 100.0
        if pct > 0:
            c.setStrokeColor(accent)
            c.setLineCap(1)
            p = c.beginPath()
            p.arc(rcx - r, rcy - r, rcx + r, rcy + r, startAng=90, extent=-360 * pct)
            c.drawPath(p, stroke=1, fill=0)
            c.setLineCap(0)
        val = f'{avg:.1f}'
        c.setFont(F['b'], 17.25)
        c.setFillColor(INK)
        vw = stringWidth(val, F['b'], 17.25) + stringWidth('%', F['r'], 8.25)
        c.drawString(rcx - vw / 2, rcy - 1, val)
        c.setFont(F['r'], 8.25)
        c.setFillColor(MUTED)
        c.drawString(rcx - vw / 2 + stringWidth(val, F['b'], 17.25), rcy - 1, '%')
        aw = stringWidth('AVERAGE', F['b'], 6.4) + 1.0 * 6
        _spaced(c, rcx - aw / 2, rcy - 12, 'AVERAGE', F['b'], 6.4, MUTED, 1.0)

    y = row_top - top_h
    c.setLineWidth(0.75)                     # the ring above uses a thick stroke
    if tiles:
        y -= 13.5
        gap = 7.5
        tw_ = (W - 2 * pad - gap * (len(tiles) - 1)) / len(tiles)
        for i, (lab, val, unit, sub) in enumerate(tiles):
            bx = L + pad + i * (tw_ + gap)
            c.setFillColor(colors.white)
            c.setStrokeColor(LINE if bw else CARD_LINE)
            c.roundRect(bx, y - tile_h, tw_, tile_h, 10.5, stroke=1, fill=1)
            c.setFont(F['sb'], 7.5)
            c.setFillColor(MUTED)
            c.drawString(bx + 10.5, y - 15, lab)
            c.setFont(F['b'], 15.75)
            c.setFillColor(INK)
            c.drawString(bx + 10.5, y - 33, val)
            if unit:
                c.setFont(F['sb'], 8.25)
                c.setFillColor(FAINT)
                c.drawString(bx + 10.5 + stringWidth(val, F['b'], 15.75) + 1.5, y - 33, unit)
            if sub:
                size = _fit(sub[0], F['sb'], 7.5, tw_ - 21, 6.2)
                c.setFont(F['sb'], size)
                c.setFillColor(sub[1])
                c.drawString(bx + 10.5, y - 47, sub[0])
        y -= tile_h
    if status:
        y -= 12 + 10
        sx = L + pad
        for lab, val, col in status:
            c.setFillColor(col)
            c.circle(sx + 3, y + 2.6, 3, stroke=0, fill=1)
            c.setFont(F['r'], 8.25)
            c.setFillColor(BODY)
            c.drawString(sx + 11, y, lab)
            vx = sx + 11 + stringWidth(lab, F['r'], 8.25) + 4
            room = R - pad - vx
            c.setFont(F['b'], _fit(val, F['b'], 8.25, room, 6.4))
            c.setFillColor(col)
            c.drawString(vx, y, val)
            sx = vx + stringWidth(val, F['b'], 8.25) + 18
        y -= 6
    y = card_top - card_h - 16.5

    # ---- subject table --------------------------------------------------------------------
    def order(rr):
        return (0 if rr.subject in CORE else 1, CORE.index(rr.subject) if rr.subject in CORE else 0, rr.subject)
    res.sort(key=order)
    show_score, show_grade, show_rem = _on(opts, 'score'), _on(opts, 'grade'), _on(opts, 'remark')
    xl = L + 10.5
    rem_w = 78 if show_rem else 0
    x_rem = R - 10.5 - rem_w
    grade_w = 52.5 if show_grade else 0
    x_grade = x_rem - grade_w - (10.5 if show_rem else 0)
    x_score_r = x_grade - (10.5 if show_grade else 0)
    reserve = 140 + (22 if _on(opts, 'grades') else 0)
    room = y - 20 - reserve
    row_h = max(19, min(42, room / max(len(res), 1)))
    fs = 10.1 if row_h >= 30 else 9
    _spaced(c, xl, y - 7, 'SUBJECT', F['b'], 7.1, MUTED, 0.9)
    if show_score:
        _spaced(c, x_score_r, y - 7, 'SCORE', F['b'], 7.1, MUTED, 0.9, align='right')
    if show_grade:
        gw = stringWidth('GRADE', F['b'], 7.1) + 0.9 * 4
        _spaced(c, x_grade + (grade_w - gw) / 2, y - 7, 'GRADE', F['b'], 7.1, MUTED, 0.9)
    if show_rem:
        _spaced(c, x_rem, y - 7, 'REMARK', F['b'], 7.1, MUTED, 0.9)
    y -= 14
    for i, r in enumerate(res):
        ab = bool(getattr(r, 'is_absent', False))
        g = None if ab else (r.grade or '')
        b = 'a' if ab else _band(g)
        if i % 2 == 0:
            c.setFillColor(zebra)
            c.roundRect(L, y - row_h, W, row_h, 7.5, stroke=0, fill=1)
        mid = y - row_h / 2
        base = mid - fs * 0.35
        c.setFont(F['sb'], fs)
        c.setFillColor(INK)
        c.drawString(xl, base, r.subject)
        if _on(opts, 'p_core') and r.subject in CORE:
            tx2 = xl + stringWidth(r.subject, F['sb'], fs) + 6
            tw2 = stringWidth('CORE', F['b'], 6.4) + 0.75 * 3 + 9
            c.setFillColor(colors.white if bw else CORE_BG)
            c.setStrokeColor(LINE)
            c.roundRect(tx2, mid - 6, tw2, 12, 3.75, stroke=1 if bw else 0, fill=1)
            _spaced(c, tx2 + 4.5, mid - 2.3, 'CORE', F['b'], 6.4, accent, 0.75)
        if show_score:
            if ab:
                _spaced(c, x_score_r, mid - 3, 'ABS', F['b'], 7.9, FAINT, 0.75, align='right')
            else:
                c.setFont(F['b'], 10.9)
                c.setFillColor(INK)
                c.drawRightString(x_score_r, mid - 3.8, '' if r.score is None else f'{r.score:g}')
        if show_grade:
            fill, txt = pills[b]
            pw, ph = 30, 16.5
            px = x_grade + (grade_w - pw) / 2
            c.setFillColor(fill)
            c.setStrokeColor(colors.HexColor('#9A9A9A'))
            c.setLineWidth(0.6)
            c.roundRect(px, mid - ph / 2, pw, ph, 6, stroke=1 if bw and b in ('p', 'f', 'a') else 0, fill=1)
            c.setFont(F['b'], 9)
            c.setFillColor(txt)
            c.drawCentredString(px + pw / 2, mid - 3.2, '—' if ab else (g or '—'))
        if show_rem:
            c.setFont(F['sb'] if b == 'f' else F['r'], 9)
            c.setFillColor(FAINT if ab else (bad if b == 'f' else BODY))
            c.drawString(x_rem, mid - 3.2, 'Absent' if ab else REMARK.get(g, '—'))
        y -= row_h

    if _on(opts, 'grades'):
        y -= 15
        kx = xl
        kx += _spaced(c, kx, y, 'GRADING', F['b'], 7.1, MUTED, 0.9) + 10
        c.setFont(F['r'], 7.1)
        c.setFillColor(MUTED)
        for g, rng in KEY:
            t = f'{g} {rng}'
            c.drawString(kx, y, t)
            kx += stringWidth(t, F['r'], 7.1) + 10

    # ---- signatures, stamp, footer -----------------------------------------------------
    foot_y = 22.5
    show_foot = _on(opts, 'p_footer') or _on(opts, 'printed_on')
    sig_base = foot_y + (30 if show_foot else 6)
    roles = {'both': ['Form teacher', 'Principal'], 'teacher': ['Form teacher'],
             'principal': ['Principal'], 'none': []}.get(signers or 'both', ['Form teacher', 'Principal'])
    stamp = _on(opts, 'p_stamp')
    sd = 61.5
    if roles or stamp:
        area = W - (sd + 19.5 if stamp else 0)
        gap = 19.5
        sw = (area - gap * (len(roles) - 1)) / len(roles) if roles else 0
        for i, role in enumerate(roles):
            sx = L + i * (sw + gap)
            c.setStrokeColor(INK)
            c.setLineWidth(0.75)
            c.line(sx, sig_base + 14, sx + sw, sig_base + 14)
            c.setFont(F['sb'], 7.5)
            c.setFillColor(MUTED)
            c.drawString(sx, sig_base, role)
            c.drawRightString(sx + sw, sig_base, 'Date')
        if stamp:
            c.setStrokeColor(colors.HexColor('#B6BCD0'))
            c.setLineWidth(0.75)
            c.setDash(2, 2)
            c.circle(R - sd / 2, sig_base + sd / 2 - 4, sd / 2, stroke=1, fill=0)
            c.setDash()
            sw2 = stringWidth('STAMP', F['b'], 6) + 1.0 * 4
            _spaced(c, R - sd / 2 - sw2 / 2, sig_base + sd / 2 - 6, 'STAMP', F['b'], 6, FAINT, 1.0)
    if show_foot:
        c.setStrokeColor(colors.HexColor('#E8EBF3'))
        c.setLineWidth(0.75)
        c.line(L, foot_y + 14, R, foot_y + 14)
        c.setFont(F['r'], 6.75)
        c.setFillColor(FAINT)
        if _on(opts, 'p_footer'):
            c.drawString(L, foot_y, f'{sname} · school examination, not an official WAEC result')
        if _on(opts, 'printed_on') and issued:
            c.drawRightString(R, foot_y, f'Issued {issued}')
