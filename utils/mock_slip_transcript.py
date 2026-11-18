"""The "Transcript" Mock WAEC result slip — a fourth theme (see
utils.mock_slip_modern for the shared helpers).

A formal progress transcript: a centred letterhead, the exam title with a
small First → Second progress card (credits and average), the student row,
a subject table that shows each subject's result in the previous mock next to
this one with the change in points, the grading key, a six-cell summary grid
(subjects, credits, distinctions, average, 5 credits incl. English & Maths,
missing core), signatures, stamp and footer. Every block can be switched off
(TRANSCRIPT_OPTIONS). Without a previous mock the progress card and the
First / Change columns simply don't appear.
"""
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont

from utils.mock_slip_modern import (CORE, KEY, REMARK, _fit, _on, _spaced, _wrap, competence_title)

_FONTS = os.path.join(os.path.dirname(__file__), '..', 'assets', 'fonts')

TRANSCRIPT_OPTIONS = [
    ('logo', 'School logo'), ('address', 'School address'), ('contact', 'Phone / email'),
    ('motto', 'School motto'),
    ('t_label', '“STATEMENT OF RESULT” label & session'), ('t_exam', 'Exam title'),
    ('t_date', 'Exam date'), ('t_progress', 'Progress card (previous → this mock)'),
    ('t_class', 'Class'), ('t_stream', 'Stream'), ('t_gender', 'Gender'),
    ('t_first', 'Previous-mock column'), ('score', 'Score column'), ('grade', 'Grade column'),
    ('t_change', 'Change column'), ('remark', 'Remark column'), ('t_core', '“CORE” tag on English & Maths'),
    ('grades', 'Grading key'),
    ('t_subjects', 'Summary — subjects sat'), ('t_credits', 'Summary — credits'),
    ('t_distinctions', 'Summary — distinctions'), ('t_average', 'Summary — average'),
    ('t_five', 'Summary — 5 credits incl. English & Maths'), ('t_missing', 'Summary — missing core'),
    ('t_stamp', 'Stamp circle'), ('t_footer', 'Footer note'), ('printed_on', 'Issued date'),
]
TRANSCRIPT_FLAGS = tuple(p for p, _ in TRANSCRIPT_OPTIONS)

INK = colors.HexColor('#1C1A1B')
BODY = colors.HexColor('#4A4447')
MUTED = colors.HexColor('#7C7174')
FAINT = colors.HexColor('#9A8F92')
GHOST = colors.HexColor('#B3A9AC')
RULE = colors.HexColor('#E7E2E3')
SOFT = colors.HexColor('#EFEBEC')
ACCENT = colors.HexColor('#7A2338')
GOOD = colors.HexColor('#1E6B45')
WARN = colors.HexColor('#8A5A00')
BAD = colors.HexColor('#A3261A')


def _fonts():
    """{'r','b','i'}: Work Sans, else Helvetica."""
    if 'TrWork' in pdfmetrics.getRegisteredFontNames():
        return {'r': 'TrWork', 'b': 'TrWork-B', 'i': 'TrWork-I'}
    try:
        for name, f in (('TrWork', 'WorkSans-Regular.ttf'), ('TrWork-B', 'WorkSans-Bold.ttf'),
                        ('TrWork-I', 'WorkSans-Italic.ttf')):
            pdfmetrics.registerFont(TTFont(name, os.path.join(_FONTS, f)))
        return {'r': 'TrWork', 'b': 'TrWork-B', 'i': 'TrWork-I'}
    except Exception:
        return {'r': 'Helvetica', 'b': 'Helvetica-Bold', 'i': 'Helvetica-Oblique'}


def _grade_color(g, bw):
    if bw:
        return INK
    if g is None:
        return GHOST
    if g == 'F9':
        return BAD
    if g in ('D7', 'E8'):
        return WARN
    return INK


def _num(v):
    return '' if v is None else f'{v:g}'


def draw_transcript_slip(c, student, summary, exam, school, opts=None, signers='both', bw=False,
                         klass='', prev=None, prev_stats=None, issued=None, prev_results=None):
    """Draw one A4 transcript slip on canvas ``c`` (caller calls showPage).

    ``prev_results`` is {subject: (score, grade, absent)} for this student in
    the previous mock (``prev``)."""
    F = _fonts()
    PW, PH = A4
    L, R = 37.5, PW - 37.5
    W = R - L
    accent = colors.black if bw else ACCENT
    good, warn, bad = (INK, INK, INK) if bw else (GOOD, WARN, BAD)
    school = school or {}
    sname = school.get('name') or 'School'
    has_prev = prev is not None and prev_results is not None
    prev_name = competence_title(prev) if prev is not None else ''
    prev_word = prev_name.split(' ')[0].upper() if prev_name else 'PREVIOUS'
    this_word = competence_title(exam).split(' ')[0].upper()

    # ---- centred letterhead -------------------------------------------------------
    y = PH - 28.5
    logo = school.get('logo_path') if _on(opts, 'logo') else None
    if logo and os.path.exists(logo):
        try:
            from reportlab.lib.utils import ImageReader
            c.drawImage(ImageReader(logo), PW / 2 - 19, y - 38, width=38, height=38, mask='auto',
                        preserveAspectRatio=True)
            y -= 44
        except Exception:
            pass
    name_up = sname.upper()
    sp = 2.6
    size = 12
    while size > 8.5 and stringWidth(name_up, F['b'], size) + sp * (len(name_up) - 1) > W:
        size -= 0.25
        sp = max(1.0, sp - 0.05)
    nw = stringWidth(name_up, F['b'], size) + sp * (len(name_up) - 1)
    _spaced(c, PW / 2 - nw / 2, y - 12, name_up, F['b'], size, INK, sp)
    y -= 16
    bits = []
    if _on(opts, 'address') and school.get('address'):
        bits.append(school['address'])
    if _on(opts, 'contact'):
        bits += [b for b in (school.get('phone'), school.get('email')) if b]
    if bits:
        line = ' · '.join(bits)
        c.setFont(F['r'], _fit(line, F['r'], 7.5, W, 6.2))
        c.setFillColor(MUTED)
        c.drawCentredString(PW / 2, y - 9, line)
        y -= 12
    motto = (school.get('motto') or '').strip() if _on(opts, 'motto') else ''
    if motto:
        c.setFont(F['i'], _fit(motto, F['i'], 7.9, W, 6.4))
        c.setFillColor(MUTED)
        c.drawCentredString(PW / 2, y - 9.5, motto)
        y -= 12.5
    y -= 10
    c.setStrokeColor(RULE)
    c.setLineWidth(0.75)
    c.line(L, y, R, y)
    y -= 16.5

    # ---- title + progress card -------------------------------------------------------
    credits = summary.get('credits') or 0
    avg = summary.get('average_score')
    show_card = _on(opts, 't_progress') and prev is not None and prev_stats is not None
    title_top = y
    card_w = 0
    if show_card:
        pc, pa = prev_stats
        card_w, card_h = 150, 54
        cx0 = R - card_w
        c.setStrokeColor(RULE)
        c.setFillColor(colors.white)
        c.roundRect(cx0, y - card_h, card_w, card_h, 9, stroke=1, fill=1)
        for i, (word, cr, av, col, strong) in enumerate(((prev_word, pc, pa, FAINT, False),
                                                          (this_word, credits, avg, accent, True))):
            colx = cx0 + 12 + i * 92 + 23
            ww = stringWidth(word, F['b'], 6.75) + 0.9 * (len(word) - 1)
            _spaced(c, colx - ww / 2, y - 14, word, F['b'], 6.75, col if strong else FAINT, 0.9)
            num = str(cr)
            c.setFont(F['b'], 11.25)
            c.setFillColor(INK if strong else MUTED)
            nwid = stringWidth(num, F['b'], 11.25) + stringWidth(' credits', F['r'], 7.1)
            c.drawString(colx - nwid / 2, y - 29, num)
            c.setFont(F['r'], 7.1)
            c.setFillColor(MUTED)
            c.drawString(colx - nwid / 2 + stringWidth(num, F['b'], 11.25), y - 29, ' credits')
            if av is not None:
                c.setFont(F['b'] if strong else F['r'], 7.5)
                c.setFillColor(INK if strong else FAINT)
                c.drawCentredString(colx, y - 42, f'{av:.1f}%')
        ax = cx0 + 62
        c.setStrokeColor(colors.HexColor('#C9BFC2'))
        c.setLineWidth(1.1)
        c.line(ax, y - 26, ax + 26, y - 26)
        c.line(ax + 22, y - 22.5, ax + 26.5, y - 26)
        c.line(ax + 22, y - 29.5, ax + 26.5, y - 26)
        c.setLineWidth(0.75)
    tw = W - (card_w + 18 if show_card else 0)
    if _on(opts, 't_label'):
        lab = 'STATEMENT OF RESULT' + (f' · {exam.session.name}' if exam.session else '')
        _spaced(c, L, y - 7, lab, F['b'], 7.5, accent, 1.5)
        y -= 13
    if _on(opts, 't_exam'):
        title = competence_title(exam)
        ts = _fit(title, F['b'], 24, tw, 15)
        c.setFont(F['b'], ts)
        c.setFillColor(INK)
        c.drawString(L, y - ts * 0.82, title)
        y -= ts + 3
    if _on(opts, 't_date') and exam.exam_date:
        c.setFont(F['r'], 8.25)
        c.setFillColor(MUTED)
        when = exam.date_label() if hasattr(exam, 'date_label') else exam.exam_date.strftime('%d %b %Y')
        c.drawString(L, y - 8, f'Written {when}')
        y -= 11
    if show_card:
        y = min(y, title_top - 54)
    y -= 15

    # ---- student row ----------------------------------------------------------------------
    details = []
    if _on(opts, 't_class') and klass:
        details.append(('CLASS', klass))
    if _on(opts, 't_stream') and getattr(student, 'stream', None):
        details.append(('STREAM', student.stream))
    if _on(opts, 't_gender') and student.gender:
        details.append(('GENDER', student.gender))
    unit = W / (2.2 + len(details))
    name_w = unit * 2.2 - 10.5
    full = student.full_name or ''
    ns = _fit(full, F['b'], 12.75, name_w, 10.5)
    lines = _wrap(full, F['b'], ns, name_w)[:2]
    row_h = 16 + len(lines) * ns * 1.18 + 8
    c.setStrokeColor(INK)
    c.setLineWidth(1.1)
    c.line(L, y, R, y)
    c.setLineWidth(0.75)
    c.setStrokeColor(RULE)
    c.line(L, y - row_h, R, y - row_h)
    _spaced(c, L, y - 13, 'STUDENT', F['b'], 6.75, FAINT, 1.2)
    c.setFont(F['b'], ns)
    c.setFillColor(INK)
    ny = y - 15
    for ln in lines:
        c.drawString(L, ny - ns * 0.95, ln)
        ny -= ns * 1.18
    for i, (lab, val) in enumerate(details):
        dx = L + unit * (2.2 + i)
        c.setStrokeColor(RULE)
        c.line(dx, y, dx, y - row_h)
        _spaced(c, dx + 10.5, y - 13, lab, F['b'], 6.75, FAINT, 1.2)
        c.setFont(F['b'], _fit(val, F['b'], 9.4, unit - 18, 7.5))
        c.setFillColor(INK)
        c.drawString(dx + 10.5, y - 26, val)
    y -= row_h + 16.5

    # ---- subject table ------------------------------------------------------------------------
    res = list(summary.get('results') or [])

    def order(r):
        return (0 if r.subject in CORE else 1, CORE.index(r.subject) if r.subject in CORE else 0, r.subject)
    res.sort(key=order)
    show_first = _on(opts, 't_first') and has_prev
    show_change = _on(opts, 't_change') and has_prev
    show_score, show_grade, show_rem = _on(opts, 'score'), _on(opts, 'grade'), _on(opts, 'remark')
    # columns right-to-left
    x = R
    col = {}
    for key, w, on in (('remark', 63, show_rem), ('change', 63, show_change), ('grade', 45, show_grade),
                       ('score', 45, show_score), ('first', 57, show_first)):
        if on:
            col[key] = (x - w, x)
            x -= w + 7.5
    subj_r = x
    # Rows share what's left above the grading key, summary grid and signatures
    # (≈125pt for signatures + stamp + footer and a gap), up to a comfortable cap.
    any_summary = any(_on(opts, k) for k in ('t_subjects', 't_credits', 't_distinctions',
                                             't_average', 't_five', 't_missing'))
    reserve = 125 + (14 if _on(opts, 'grades') else 0) + (76 if any_summary else 0)
    room = y - 13 - reserve
    rh = max(19, min(50, room / max(len(res), 1)))
    fs = 10.1 if rh >= 30 else 9

    def head(key, text, align):
        a, b = col[key]
        tw2 = stringWidth(text, F['b'], 6.75) + 1.05 * (len(text) - 1)
        if align == 'right':
            _spaced(c, b - tw2, y - 7, text, F['b'], 6.75, MUTED, 1.05)
        elif align == 'center':
            _spaced(c, (a + b) / 2 - tw2 / 2, y - 7, text, F['b'], 6.75, MUTED, 1.05)
        else:
            _spaced(c, a + (7.5 if key == 'remark' else 0), y - 7, text, F['b'], 6.75, MUTED, 1.05)
    _spaced(c, L + 1.5, y - 7, 'SUBJECT', F['b'], 6.75, MUTED, 1.05)
    if show_first:
        head('first', prev_word, 'center')
    if show_score:
        head('score', 'SCORE', 'right')
    if show_grade:
        head('grade', 'GRADE', 'center')
    if show_change:
        head('change', 'CHANGE', 'right')
    if show_rem:
        head('remark', 'REMARK', 'left')
    y -= 12.5
    c.setStrokeColor(INK)
    c.setLineWidth(0.75)
    c.line(L, y, R, y)
    for r in res:
        ab = bool(getattr(r, 'is_absent', False))
        g = None if ab else (r.grade or None)
        mid = y - rh / 2
        base = mid - fs * 0.35
        c.setFont(F['r'], fs)
        c.setFillColor(INK)
        c.drawString(L + 1.5, base, r.subject)
        if _on(opts, 't_core') and r.subject in CORE:
            _spaced(c, L + 1.5 + stringWidth(r.subject, F['r'], fs) + 6, base + 0.5, 'CORE', F['b'], 6.75, accent, 0.9)
        p = (prev_results or {}).get(r.subject) if has_prev else None
        if show_first:
            a, b = col['first']
            c.setFont(F['r'], 8.6)
            c.setFillColor(FAINT)
            if p is None:
                txt = '—'
            elif p[2]:
                txt = 'ABS'
            else:
                txt = f'{p[1] or "—"} · {_num(p[0])}'
            c.drawCentredString((a + b) / 2, mid - 3, txt)
        if show_score:
            a, b = col['score']
            if ab:
                _spaced(c, b - stringWidth('ABS', F['b'], 7.9) - 1.5, mid - 3, 'ABS', F['b'], 7.9, GHOST, 0.75)
            else:
                c.setFont(F['b'], 10.5)
                c.setFillColor(INK)
                c.drawRightString(b, mid - 3.8, _num(r.score))
        if show_grade:
            a, b = col['grade']
            c.setFont(F['b'], 11.25)
            c.setFillColor(_grade_color(g, bw))
            c.drawCentredString((a + b) / 2, mid - 4, g or '—')
        if show_change:
            a, b = col['change']
            c.setFont(F['b'], 8.6)
            if ab:
                c.setFillColor(GHOST)
                c.drawRightString(b, mid - 3, 'missed')
            elif p is None or p[2] or p[0] is None or r.score is None:
                c.setFillColor(FAINT)
                c.drawRightString(b, mid - 3, 'new' if p is None else '—')
            else:
                d = round(r.score - p[0], 1)
                d = int(d) if d == int(d) else d
                if d == 0:
                    c.setFillColor(FAINT)
                    c.drawRightString(b, mid - 3, '—')
                else:
                    colr = good if d > 0 else bad
                    txt = f'+{d}' if d > 0 else f'−{abs(d)}'
                    tx = b - stringWidth(txt, F['b'], 8.6)
                    c.setFillColor(colr)
                    c.drawString(tx, mid - 3, txt)
                    # triangle marker, drawn (no font glyph needed)
                    t = c.beginPath()
                    tx -= 10
                    if d > 0:
                        t.moveTo(tx, mid - 3); t.lineTo(tx + 7, mid - 3); t.lineTo(tx + 3.5, mid + 3.5)
                    else:
                        t.moveTo(tx, mid + 3.5); t.lineTo(tx + 7, mid + 3.5); t.lineTo(tx + 3.5, mid - 3)
                    t.close()
                    c.drawPath(t, stroke=0, fill=1)
        if show_rem:
            a, b = col['remark']
            c.setFont(F['i'] if ab else F['r'], 8.6)
            c.setFillColor(GHOST if ab else (bad if g == 'F9' else BODY))
            c.drawString(a + 7.5, mid - 3, 'Absent' if ab else REMARK.get(g, '—'))
        y -= rh
        c.setStrokeColor(SOFT)
        c.line(L, y, R, y)

    if _on(opts, 'grades'):
        y -= 14
        kx = L + 1.5
        kx += _spaced(c, kx, y, 'GRADING', F['b'], 6.75, MUTED, 1.05) + 10
        c.setFont(F['r'], 7.1)
        c.setFillColor(MUTED)
        for gk, rng in KEY:
            t = f'{gk} {rng}'
            c.drawString(kx, y, t)
            kx += stringWidth(t, F['r'], 7.1) + 10

    # ---- summary grid --------------------------------------------------------------------------
    res_all = list(summary.get('results') or [])
    absent = sum(1 for r in res_all if getattr(r, 'is_absent', False))
    missing = list(summary.get('missing_core') or [])
    short = {'English Language': 'English', 'Mathematics': 'Maths'}
    cells = []
    if _on(opts, 't_subjects'):
        cells.append(('Subjects sat', f'{len(res_all) - absent} of {len(res_all)}', warn if absent else INK))
    if _on(opts, 't_credits'):
        cells.append(('Credits (A1–C6)', str(credits), INK))
    if _on(opts, 't_distinctions'):
        cells.append(('Distinctions (A1–B3)', str(summary.get('distinctions') or 0), INK))
    if _on(opts, 't_average'):
        cells.append(('Average', f'{avg:.1f}%' if avg is not None else '—', INK))
    if _on(opts, 't_five'):
        ok = bool(summary.get('has_5_incl_core'))
        cells.append(('5 credits incl. Eng & Maths', 'Yes' if ok else 'No', good if ok else bad))
    if _on(opts, 't_missing'):
        cells.append(('Missing core', ', '.join(short.get(m, m) for m in missing) if missing else 'None',
                      bad if missing else good))
    if cells:
        y -= 18
        cols = 2 if len(cells) == 4 else min(3, len(cells))      # 4 items read best as 2 × 2
        nrows = (len(cells) + cols - 1) // cols
        ch = 28.5
        cw = W / cols
        c.setStrokeColor(RULE)
        c.roundRect(L, y - ch * nrows, W, ch * nrows, 10.5, stroke=1, fill=0)
        for i, (lab, val, colr) in enumerate(cells):
            rr, cc = divmod(i, cols)
            x0, y0 = L + cc * cw, y - rr * ch
            if cc:
                c.line(x0, y0, x0, y0 - ch)
            if rr:
                c.line(x0, y0, x0 + cw, y0)
            c.setFont(F['r'], 8.25)
            c.setFillColor(MUTED)
            c.drawString(x0 + 12, y0 - ch / 2 - 3, lab)
            room = cw - 24 - stringWidth(lab, F['r'], 8.25) - 8
            vs = _fit(val, F['b'], 11.25, room, 7.5)
            c.setFont(F['b'], vs)
            c.setFillColor(colr)
            c.drawRightString(x0 + cw - 12, y0 - ch / 2 - 3.5, val)
        y -= ch * nrows

    # ---- signatures, stamp, footer -------------------------------------------------------------
    foot_y = 21
    show_foot = _on(opts, 't_footer') or _on(opts, 'printed_on')
    sig_base = foot_y + (24 if show_foot else 6)
    roles = {'both': ['Form teacher', 'Principal'], 'teacher': ['Form teacher'],
             'principal': ['Principal'], 'none': []}.get(signers or 'both', ['Form teacher', 'Principal'])
    stamp = _on(opts, 't_stamp')
    sd = 60
    if roles or stamp:
        area = W - (sd + 19.5 if stamp else 0)
        gap = 19.5
        sw = (area - gap * (len(roles) - 1)) / len(roles) if roles else 0
        for i, role in enumerate(roles):
            sx = L + i * (sw + gap)
            c.setStrokeColor(INK)
            c.setLineWidth(0.75)
            c.line(sx, sig_base + 14, sx + sw, sig_base + 14)
            c.setFont(F['r'], 7.5)
            c.setFillColor(MUTED)
            c.drawString(sx, sig_base, role)
            c.drawRightString(sx + sw, sig_base, 'Date')
        if stamp:
            c.setStrokeColor(colors.HexColor('#C9BFC2'))
            c.setDash(2, 2)
            c.circle(R - sd / 2, sig_base + sd / 2 - 4, sd / 2, stroke=1, fill=0)
            c.setDash()
            sw2 = stringWidth('STAMP', F['b'], 6) + 1.2 * 4
            _spaced(c, R - sd / 2 - sw2 / 2, sig_base + sd / 2 - 6, 'STAMP', F['b'], 6, FAINT, 1.2)
    if show_foot:
        c.setFont(F['r'], 6.75)
        c.setFillColor(FAINT)
        if _on(opts, 't_footer'):
            c.drawString(L, foot_y, f'{sname} · school examination — not an official WAEC result')
        if _on(opts, 'printed_on') and issued:
            c.drawRightString(R, foot_y, f'Issued {issued}')
