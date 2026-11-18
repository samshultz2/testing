"""The "Modern" Mock WAEC result slip — a second theme beside the classic
"Competence Result" statement (utils.mock_waec_pdf.result_slips_pdf).

A clean A4 page that prints cheaply and reads well as a PDF or image:
a thin accent stripe, the school letterhead, the exam title, the student,
a three-figure summary (subjects, credits, average, with the change since the
previous mock), the subject table with tinted grade pills, the grading key,
signatures and a footer. Every block can be switched off (see MODERN_OPTIONS).
"""
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont

_FONTS = os.path.join(os.path.dirname(__file__), '..', 'assets', 'fonts')

# (param, label) for the export screen, all on by default. Shared params
# (logo, address, contact, motto, score, grade, remark, grades, printed_on)
# mean the same thing on the classic slip.
MODERN_OPTIONS = [
    ('m_stripe', 'Accent stripe at the top'),
    ('logo', 'School logo'), ('address', 'School address'), ('contact', 'Phone / email'),
    ('motto', 'School motto'),
    ('m_label', '“RESULT SLIP” label'), ('m_exam', 'Exam title'),
    ('m_session', 'Session'), ('m_date', 'Exam date'),
    ('m_class', 'Class'), ('m_gender', 'Gender'),
    ('m_subjects', 'Summary — subjects'), ('m_credits', 'Summary — credits'),
    ('m_average', 'Summary — average'), ('m_change', 'Change since the previous mock'),
    ('m_sn', 'Row numbers (#)'), ('m_core', '“CORE” tag on English & Maths'),
    ('score', 'Score column'), ('grade', 'Grade column'), ('remark', 'Remark column'),
    ('grades', 'Grading key'), ('m_stamp', 'Stamp circle'),
    ('m_footer', 'Footer note'), ('printed_on', 'Issued date'),
]
MODERN_FLAGS = tuple(p for p, _ in MODERN_OPTIONS)

INK = colors.HexColor('#161B26')
MUTED = colors.HexColor('#5D6578')
FAINT = colors.HexColor('#8A91A3')
RULE = colors.HexColor('#E3E6EC')
SOFT_RULE = colors.HexColor('#D5D9E2')
PANEL = colors.HexColor('#F5F6F9')
ACCENT = colors.HexColor('#26345F')
GOOD = colors.HexColor('#145440')
WARN = colors.HexColor('#774700')
BAD = colors.HexColor('#9A2216')

# grade band -> (pill fill, pill text)
PILLS = {
    'd': (colors.HexColor('#E3F1EB'), colors.HexColor('#145440')),
    'c': (colors.HexColor('#E7ECF7'), colors.HexColor('#24427A')),
    'p': (colors.HexColor('#FBEED8'), colors.HexColor('#774700')),
    'f': (colors.HexColor('#FBE3E0'), colors.HexColor('#9A2216')),
    'a': (colors.HexColor('#F0F1F4'), colors.HexColor('#5D6578')),
}
PILLS_BW = {
    'd': (colors.HexColor('#D9D9D9'), colors.black), 'c': (colors.HexColor('#EDEDED'), colors.black),
    'p': (colors.white, colors.black), 'f': (colors.white, colors.black), 'a': (colors.white, colors.HexColor('#555555')),
}
REMARK = {'A1': 'Excellent', 'B2': 'Very good', 'B3': 'Good', 'C4': 'Credit', 'C5': 'Credit',
          'C6': 'Credit', 'D7': 'Pass', 'E8': 'Pass', 'F9': 'Fail'}
CORE = ('English Language', 'Mathematics')
KEY = [('A1', '75–100'), ('B2', '70–74'), ('B3', '65–69'), ('C4', '60–64'), ('C5', '55–59'),
       ('C6', '50–54'), ('D7', '45–49'), ('E8', '40–44'), ('F9', '0–39')]


def _band(g):
    g = (g or '').upper()
    if g in ('A1', 'B2', 'B3'):
        return 'd'
    if g in ('C4', 'C5', 'C6'):
        return 'c'
    if g in ('D7', 'E8'):
        return 'p'
    if g == 'F9':
        return 'f'
    return 'a'


def _fonts():
    """{'r','m','sb','b','h'} font names: Inter for text, Plus Jakarta Sans
    ExtraBold for the headline figures; Helvetica if the files are missing."""
    names = pdfmetrics.getRegisteredFontNames()
    if 'MsInter' in names:
        return {'r': 'MsInter', 'm': 'MsInter-M', 'sb': 'MsInter-SB', 'b': 'MsInter-B', 'h': 'MsHead'}
    try:
        for name, f in (('MsInter', 'Inter-Regular.ttf'), ('MsInter-M', 'Inter-Medium.ttf'),
                        ('MsInter-SB', 'Inter-SemiBold.ttf'), ('MsInter-B', 'Inter-Bold.ttf')):
            pdfmetrics.registerFont(TTFont(name, os.path.join(_FONTS, f)))
        head = os.path.join(_FONTS, 'PlusJakartaSans-ExtraBold.ttf')
        pdfmetrics.registerFont(TTFont('MsHead', head if os.path.exists(head)
                                       else os.path.join(_FONTS, 'Inter-Bold.ttf')))
        return {'r': 'MsInter', 'm': 'MsInter-M', 'sb': 'MsInter-SB', 'b': 'MsInter-B', 'h': 'MsHead'}
    except Exception:
        return {'r': 'Helvetica', 'm': 'Helvetica', 'sb': 'Helvetica-Bold', 'b': 'Helvetica-Bold',
                'h': 'Helvetica-Bold'}


def _on(opts, key):
    return (opts or {}).get(key, True) is not False


def competence_title(exam):
    """'Second Mock WAEC' -> 'Second Competence'."""
    name = exam.display_name or ''
    return name.replace('Mock WAEC', 'Competence').strip() or 'Competence'


def _signed(v):
    if v is None:
        return ''
    v = round(v, 1)
    if v == int(v):
        v = int(v)
    return f'+{v}' if v > 0 else (f'−{abs(v)}' if v < 0 else '0')


def _fit(text, font, size, width, min_size):
    """Largest size (down to min_size) at which text fits width."""
    while size > min_size and stringWidth(text, font, size) > width:
        size -= 0.25
    return size


def _wrap(text, font, size, width):
    words, lines, cur = text.split(), [], ''
    for w in words:
        t = (cur + ' ' + w).strip()
        if stringWidth(t, font, size) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _spaced(c, x, y, text, font, size, color, spacing=1.0, align='left'):
    """Letter-spaced small caps label."""
    w = stringWidth(text, font, size) + spacing * max(len(text) - 1, 0)
    if align == 'right':
        x -= w
    t = c.beginText(x, y)
    t.setFont(font, size)
    t.setFillColor(color)
    t.setCharSpace(spacing)
    t.textOut(text)
    t.setCharSpace(0)            # don't let the spacing leak into later text
    c.drawText(t)
    return w


def draw_modern_slip(c, student, summary, exam, school, opts=None, signers='both', bw=False,
                     klass='', prev=None, prev_stats=None, issued=None):
    """Draw one A4 slip on canvas ``c`` (caller calls showPage).

    ``summary`` is MockWAECAnalytics._summarise(...) plus ``results``;
    ``prev`` the previous mock (or None) and ``prev_stats`` this student's
    (credits, average) in it."""
    F = _fonts()
    PW, PH = A4
    M = 39                                   # side margin
    accent = colors.black if bw else ACCENT
    pills = PILLS_BW if bw else PILLS
    good, warn, bad = (INK, INK, INK) if bw else (GOOD, WARN, BAD)
    school = school or {}
    W = PW - 2 * M

    # ---- accent stripe ------------------------------------------------------
    if _on(opts, 'm_stripe'):
        c.setFillColor(accent)
        c.rect(0, PH - 4.5, PW, 4.5, stroke=0, fill=1)
    y = PH - 33

    # ---- letterhead -----------------------------------------------------------
    x = M
    logo = school.get('logo_path') if _on(opts, 'logo') else None
    if logo and os.path.exists(logo):
        try:
            from reportlab.lib.utils import ImageReader
            ir = ImageReader(logo)
            iw, ih = ir.getSize()
            h = 36
            w = min(h * (iw / ih) if ih else h, 54)
            c.drawImage(ir, M, y - h + 4, width=w, height=h, mask='auto', preserveAspectRatio=True)
            x = M + w + 10.5
        except Exception:
            x = M
    motto = (school.get('motto') or '').strip() if _on(opts, 'motto') else ''
    motto_w = min(stringWidth(motto, F['sb'], 8), W * 0.32) if motto else 0
    name = school.get('name') or 'School'
    nsize = _fit(name, F['h'], 12.75, W - (x - M) - motto_w - 12, 9)
    c.setFillColor(INK)
    c.setFont(F['h'], nsize)
    c.drawString(x, y - 12, name)
    bits = []
    if _on(opts, 'address') and school.get('address'):
        bits.append(school['address'])
    if _on(opts, 'contact'):
        bits += [b for b in (school.get('phone'), school.get('email')) if b]
    if bits:
        line = ' · '.join(bits)
        size = _fit(line, F['r'], 8, W - (x - M) - motto_w - 12, 6.5)
        c.setFont(F['r'], size)
        c.setFillColor(MUTED)
        c.drawString(x, y - 24.5, line)
    if motto:
        msize = _fit(motto, F['sb'], 8, motto_w, 6.5)
        c.setFont(F['sb'], msize)
        c.setFillColor(MUTED)
        c.drawRightString(PW - M, y - 18, motto)
    y -= 36 + 22.5

    # ---- title + session / date -------------------------------------------------
    meta = []
    if _on(opts, 'm_session') and exam.session:
        meta.append(('Session', exam.session.name))
    if _on(opts, 'm_date') and exam.exam_date:
        meta.append(('Exam date', exam.date_label() if hasattr(exam, 'date_label') else exam.exam_date.strftime('%d %b %Y')))
    show_label, show_exam = _on(opts, 'm_label'), _on(opts, 'm_exam')
    if show_label or show_exam or meta:
        top = y
        if show_label:
            _spaced(c, M, y - 7, 'RESULT SLIP', F['b'], 7.9, accent, 1.25)
            y -= 13
        if show_exam:
            title = competence_title(exam)
            tsize = _fit(title, F['h'], 22.5, W * 0.62, 15)
            c.setFillColor(INK)
            c.setFont(F['h'], tsize)
            c.drawString(M, y - tsize * 0.82, title)
            y -= tsize + 2
        if meta:
            my = top - 16 if (show_label or show_exam) else top - 8
            for label, val in meta:
                c.setFont(F['r'], 8.25)
                c.setFillColor(MUTED)
                vw = stringWidth(val, F['b'], 8.25)
                c.drawRightString(PW - M - vw - 13.5, my, label)
                c.setFont(F['b'], 8.25)
                c.setFillColor(INK)
                c.drawRightString(PW - M, my, val)
                my -= 13
            y = min(y, my + 4)
        y -= 13.5
        c.setStrokeColor(RULE)
        c.setLineWidth(0.75)
        c.line(M, y, PW - M, y)
        y -= 16.5

    # ---- student ------------------------------------------------------------------
    _spaced(c, M, y - 7, 'STUDENT', F['b'], 7.5, MUTED, 0.9)
    y -= 12
    full = student.full_name or ''
    nsize = _fit(full, F['h'], 16.5, W, 13)
    lines = _wrap(full, F['h'], nsize, W)[:2]
    c.setFillColor(INK)
    c.setFont(F['h'], nsize)
    for ln in lines:
        c.drawString(M, y - nsize * 0.85, ln)
        y -= nsize * 1.2
    details = []
    if _on(opts, 'm_class') and klass:
        details.append(('CLASS', klass))
    if _on(opts, 'm_gender') and student.gender:
        details.append(('GENDER', student.gender))
    if details:
        y -= 7
        col = (W - 30) / 3
        for i, (lab, val) in enumerate(details):
            cx = M + i * (col + 15)
            _spaced(c, cx, y - 7, lab, F['b'], 7.5, MUTED, 0.9)
            c.setFont(F['b'], 10)
            c.setFillColor(INK)
            c.drawString(cx, y - 21, val[:48])
        y -= 27
    y -= 16.5

    # ---- summary strip --------------------------------------------------------------
    res = list(summary.get('results') or [])
    n_all = len(res)
    absent = sum(1 for r in res if getattr(r, 'is_absent', False))
    sat = n_all - absent
    credits = summary.get('credits') or 0
    avg = summary.get('average_score')
    show_change = _on(opts, 'm_change') and prev is not None and prev_stats is not None
    prev_name = competence_title(prev) if prev is not None else ''
    cells = []
    if _on(opts, 'm_subjects'):
        cells.append(('SUBJECTS', str(sat), f' of {n_all}' if absent else '',
                      (f'{absent} paper{"s" if absent != 1 else ""} missed', warn) if absent else ('All papers sat', MUTED)))
    if _on(opts, 'm_credits'):
        sub = None
        if show_change:
            d = credits - (prev_stats[0] or 0)
            sub = (f'{_signed(d)} since {prev_name}', good if d > 0 else (bad if d < 0 else MUTED))
        cells.append(('CREDITS', str(credits), ' A1–C6', sub))
    if _on(opts, 'm_average'):
        sub = None
        if show_change and avg is not None and prev_stats[1] is not None:
            d = round(avg - prev_stats[1], 1)
            sub = (f'{_signed(d)} since {prev_name}', good if d > 0 else (bad if d < 0 else MUTED))
        cells.append(('AVERAGE', f'{avg:.1f}' if avg is not None else '—', '%' if avg is not None else '', sub))
    if cells:
        h = 57 if any(cl[3] for cl in cells) else 46
        c.setFillColor(colors.white if bw else PANEL)
        c.setStrokeColor(SOFT_RULE if bw else PANEL)
        c.roundRect(M, y - h, W, h, 10.5, stroke=1 if bw else 0, fill=1)
        cw = W / len(cells)
        for i, (lab, val, unit, sub) in enumerate(cells):
            cx = M + i * cw + 13.5
            if i:
                c.setStrokeColor(RULE)
                c.setLineWidth(0.75)
                c.line(M + i * cw, y - h, M + i * cw, y)
            _spaced(c, cx, y - 15, lab, F['b'], 7.5, MUTED, 0.9)
            c.setFont(F['h'], 18)
            c.setFillColor(INK)
            c.drawString(cx, y - 35, val)
            if unit:
                c.setFont(F['sb'], 9)
                c.setFillColor(MUTED)
                c.drawString(cx + stringWidth(val, F['h'], 18) + 2, y - 35, unit)
            if sub:
                c.setFont(F['sb'], 7.9)
                c.setFillColor(sub[1])
                c.drawString(cx, y - 48, sub[0][:46])
        y -= h + 19.5

    # ---- subject table ------------------------------------------------------------
    def order(r):
        return (0 if r.subject in CORE else 1, CORE.index(r.subject) if r.subject in CORE else 0, r.subject)
    res.sort(key=order)
    show_sn, show_score, show_grade, show_rem = (_on(opts, 'm_sn'), _on(opts, 'score'),
                                                 _on(opts, 'grade'), _on(opts, 'remark'))
    sn_w = 21 if show_sn else 0
    rem_w = 90 if show_rem else 0
    grade_w = 60 if show_grade else 0
    score_w = 67.5 if show_score else 0
    x_subj = M + 3 + sn_w
    x_rem = PW - M - rem_w
    x_grade = x_rem - grade_w - (9 if show_rem else 0)
    x_score_r = x_grade - (9 if show_grade else 0)
    # Row height: as tall as the design (34.5pt) when there's room, tighter for
    # long subject lists so everything stays on one page.
    reserve = 150 + (24 if _on(opts, 'grades') else 0)
    avail = y - 22 - reserve
    row_h = max(20, min(34.5, avail / max(len(res), 1)))
    fs = 10.1 if row_h >= 28 else 9
    _spaced(c, M + 3, y - 7, '#' if show_sn else '', F['b'], 7.5, INK, 0.9)
    _spaced(c, x_subj, y - 7, 'SUBJECT', F['b'], 7.5, INK, 0.9)
    if show_score:
        _spaced(c, x_score_r, y - 7, 'SCORE', F['b'], 7.5, INK, 0.9, align='right')
    if show_grade:
        gw = stringWidth('GRADE', F['b'], 7.5) + 0.9 * 4
        _spaced(c, x_grade + (grade_w - gw) / 2, y - 7, 'GRADE', F['b'], 7.5, INK, 0.9)
    if show_rem:
        _spaced(c, x_rem, y - 7, 'REMARK', F['b'], 7.5, INK, 0.9)
    y -= 13
    c.setStrokeColor(INK)
    c.setLineWidth(1.1)
    c.line(M, y, PW - M, y)
    for i, r in enumerate(res):
        ab = bool(getattr(r, 'is_absent', False))
        g = None if ab else (r.grade or '')
        b = 'a' if ab else _band(g)
        mid = y - row_h / 2
        base = mid - fs * 0.35
        if show_sn:
            c.setFont(F['r'], 8.25)
            c.setFillColor(FAINT)
            c.drawString(M + 3, base, str(i + 1))
        c.setFont(F['m'], fs)
        c.setFillColor(INK)
        subj = r.subject
        max_sw = (x_score_r - 60 if show_score else (x_grade if show_grade else x_rem)) - x_subj - 8
        c.drawString(x_subj, base, subj if stringWidth(subj, F['m'], fs) <= max_sw else subj[:30])
        if _on(opts, 'm_core') and r.subject in CORE:
            tx = x_subj + stringWidth(subj, F['m'], fs) + 6
            tw = stringWidth('CORE', F['b'], 6.75) + 0.6 * 3 + 7.5
            c.setStrokeColor(SOFT_RULE)
            c.setLineWidth(0.75)
            c.roundRect(tx, mid - 6, tw, 12, 3, stroke=1, fill=0)
            _spaced(c, tx + 3.75, mid - 2.5, 'CORE', F['b'], 6.75, MUTED, 0.6)
        if show_score:
            if ab:
                _spaced(c, x_score_r, mid - 3, 'ABS', F['b'], 8.25, FAINT, 0.6, align='right')
            else:
                c.setFont(F['b'], 10.5)
                c.setFillColor(INK)
                c.drawRightString(x_score_r, base, '' if r.score is None else f'{r.score:g}')
        if show_grade:
            fill, txt = pills[b]
            pw, ph = 31.5, 18
            px = x_grade + (grade_w - pw) / 2
            c.setFillColor(fill)
            c.setStrokeColor(colors.HexColor('#9A9A9A') if bw and b in ('p', 'f', 'a') else fill)
            c.setLineWidth(0.6)
            c.roundRect(px, mid - ph / 2, pw, ph, 4.5, stroke=1 if bw else 0, fill=1)
            c.setFont(F['b'], 9)
            c.setFillColor(txt)
            c.drawCentredString(px + pw / 2, mid - 3.2, '—' if ab else (g or '—'))
        if show_rem:
            c.setFont(F['m'], 9)
            c.setFillColor(FAINT if ab else (bad if b == 'f' else colors.HexColor('#3B4253')))
            c.drawString(x_rem, mid - 3.2, 'Absent' if ab else REMARK.get(g, '—'))
        y -= row_h
        c.setStrokeColor(RULE)
        c.setLineWidth(0.75)
        c.line(M, y, PW - M, y)

    if _on(opts, 'grades'):
        y -= 15
        kx = M + 3
        kx += _spaced(c, kx, y, 'GRADING', F['b'], 7.5, MUTED, 0.9) + 10
        c.setFont(F['r'], 7.5)
        c.setFillColor(MUTED)
        for g, rng in KEY:
            t = f'{g} {rng}'
            c.drawString(kx, y, t)
            kx += stringWidth(t, F['r'], 7.5) + 9.5

    # ---- signatures + stamp (bottom) ----------------------------------------------
    foot_y = 30
    show_foot = _on(opts, 'm_footer') or _on(opts, 'printed_on')
    sig_base = foot_y + (32 if show_foot else 6)
    roles = {'both': ['Form teacher', 'Principal'], 'teacher': ['Form teacher'],
             'principal': ['Principal'], 'none': []}.get(signers or 'both', ['Form teacher', 'Principal'])
    stamp = _on(opts, 'm_stamp')
    stamp_d = 63
    if roles or stamp:
        area = W - (stamp_d + 21 if stamp else 0)
        gap = 21
        sw = (area - gap * (len(roles) - 1)) / len(roles) if roles else 0
        for i, role in enumerate(roles):
            sx = M + i * (sw + gap)
            c.setStrokeColor(INK)
            c.setLineWidth(0.75)
            c.line(sx, sig_base + 14, sx + sw, sig_base + 14)
            c.setFont(F['sb'], 7.9)
            c.setFillColor(MUTED)
            c.drawString(sx, sig_base, role)
            c.drawRightString(sx + sw, sig_base, 'Date')
        if stamp:
            c.setStrokeColor(colors.HexColor('#B9BFCC'))
            c.setLineWidth(0.75)
            c.setDash(2, 2)
            c.circle(PW - M - stamp_d / 2, sig_base + stamp_d / 2 - 4, stamp_d / 2, stroke=1, fill=0)
            c.setDash()
            _spaced(c, PW - M - stamp_d / 2 - 15, sig_base + stamp_d / 2 - 7, 'STAMP', F['b'], 6.4, FAINT, 0.9)

    if show_foot:
        c.setStrokeColor(RULE)
        c.setLineWidth(0.75)
        c.line(M, foot_y + 15, PW - M, foot_y + 15)
        c.setFont(F['r'], 7.1)
        c.setFillColor(FAINT)
        if _on(opts, 'm_footer'):
            c.drawString(M, foot_y, f'{name} · Competence result slip · school examination, not an official WAEC result')
        if _on(opts, 'printed_on') and issued:
            c.drawRightString(PW - M, foot_y, f'Issued {issued}')
