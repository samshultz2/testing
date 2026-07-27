"""Certificate **layout archetypes** — genuinely distinct structures.

Each layout is a different *composition* (header arrangement, photo/seal/QR
placement, details-grid shape, signature block), not a recolour of one design.
Every layout also fills the page: header + certifying text + a student-details
grid + a full authentication cluster (serial, seal, rubber stamp, barcode,
signatures, issue meta) are distributed over the whole body so no vertical
whitespace is left at the foot.

A layout is bound to a distinct theme, so no two published templates share both
structure and palette. ``LAYOUTS`` is the registry the certificate engine reads.
"""
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, HRFlowable

from utils import doc_themes as th

L_W = th.L_W
_AVAIL = th._L_BODY_H


def _col(v):
    return colors.HexColor(v) if isinstance(v, str) else v


def _P(text, font, size, color, align=TA_CENTER, leading=None, sa=0, sb=0):
    return Paragraph(str(text), ParagraphStyle(
        'x', fontName=font, fontSize=size, textColor=_col(color), alignment=align,
        leading=leading or size * 1.2, spaceAfter=sa, spaceBefore=sb))


def _logo(h=15, w=42):
    return th._logo(max_h=h, max_w=w)


def _measure(flowables, width):
    total = 0
    for f in (flowables or []):
        try:
            total += f.getSpaceBefore()
        except Exception:
            pass
        try:
            total += f.wrap(width, 2000)[1]
        except Exception:
            pass
        try:
            total += f.getSpaceAfter()
        except Exception:
            pass
    return total


def _bands(top, mid, bot, avail, width, ratios=(0.30, 0.44, 0.26),
           valigns=None, halign='CENTER'):
    """Stack three groups and insert *elastic* gaps so the content fills the full
    body height without ever forcing a row to overflow (which would overlap the
    next group). ``ratios`` biases how the slack is split between the gaps."""
    groups = [list(top or []), list(mid or []), list(bot or [])]
    used = sum(_measure(g, width) for g in groups)
    slack = max(0, avail - used)
    # two gaps: after top, after mid. Bias by the trailing ratios so signatures sink.
    g1 = slack * (ratios[1] / (ratios[1] + ratios[2])) if (ratios[1] + ratios[2]) else slack / 2
    g2 = slack - g1
    out = groups[0]
    if g1 > 2:
        out = out + [Spacer(1, g1)]
    out = out + groups[1]
    if g2 > 2:
        out = out + [Spacer(1, g2)]
    out = out + groups[2]
    return out


def _details(fields, theme, width, cols=3, boxed=False):
    """A student-details grid (label over underlined value), ``cols`` wide."""
    hfont, bfont, _n = th.fonts(theme)
    primary = _col(theme['primary'])
    items = [(k, v) for k, v in (fields or []) if v]
    if not items:
        return Spacer(1, 0)
    cells, row = [], []
    cw = width / cols
    for k, v in items:
        row.append([_P(k.upper(), hfont, 7.2, colors.Color(*primary.rgb(), alpha=0.7), TA_LEFT, sa=1),
                    _P(v, bfont, 9.5, '#111827', TA_LEFT)])
        if len(row) == cols:
            cells.append(row); row = []
    if row:
        while len(row) < cols:
            row.append('')
        cells.append(row)
    t = Table(cells, colWidths=[cw] * cols)
    style = [('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 4),
             ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
             ('LINEBELOW', (0, 0), (-1, -1), 0.4, colors.Color(*primary.rgb(), alpha=0.3))]
    if boxed:
        style += [('BOX', (0, 0), (-1, -1), 0.6, primary),
                  ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.Color(*primary.rgb(), alpha=0.2))]
    t.setStyle(TableStyle(style))
    return t


def _sig_cell(label, theme):
    _h, bfont, _n = th.fonts(theme)
    return [_P('_______________________', bfont, 10, '#334155'),
            _P(f'<b>{label}</b>', bfont, 8.5, '#334155')]


def _auth(content, theme, width, layout='row'):
    """Authentication cluster: rubber stamp · signatures · gold seal · barcode+serial."""
    _h, bfont, _n = th.fonts(theme)
    labels = content.get('signatures') or ['Principal', 'Registrar']
    stamp = th.rubber_stamp(theme, top=content.get('seal_text') or 'OFFICIAL', mid='SEAL')
    seal = th.gold_seal(theme)
    bc = th.barcode(content.get('serial'))
    sigs = labels[:3]
    n = len(sigs)
    sig_tbl = Table([[_sig_cell(s, theme)[0] for s in sigs],
                     [_sig_cell(s, theme)[1] for s in sigs]], colWidths=[ (width - 58*mm) / n ] * n)
    sig_tbl.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('TOPPADDING', (0, 1), (-1, 1), 1)]))
    top = Table([[stamp, sig_tbl, seal]], colWidths=[28 * mm, width - 58 * mm, 28 * mm])
    top.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
    out = [top]
    meta = content.get('meta')
    if bc is not None:
        strip = Table([[bc, _P((meta or '') + '  ·  S/N: ' + str(content.get('serial') or ''),
                               bfont, 8, theme['accent'], TA_LEFT)]],
                      colWidths=[86 * mm, width - 86 * mm])
        strip.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                                   ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                                   ('LEFTPADDING', (1, 0), (1, 0), 8),
                                   ('TOPPADDING', (0, 0), (-1, -1), 4)]))
        out.append(strip)
    elif meta:
        out.append(_P(meta, bfont, 9, theme['accent']))
    return out


def _title(content, theme, size=26):
    hfont, _b, _n = th.fonts(theme)
    return _P(content['title'].upper(), hfont, size, theme['primary'], leading=size * 1.12)


def _kicker(content, theme):
    hfont, bfont, _n = th.fonts(theme)
    els = [_P(content['kicker'].upper(), hfont, 13, theme['gold'], sa=1)]
    if content.get('motto'):
        els.append(_P(f"<i>{content['motto']}</i>", bfont, 8.5, theme['accent']))
    return els


def _hero(content, theme, lead=True):
    _h, bfont, nfont = th.fonts(theme)
    els = []
    if lead and content.get('lead'):
        els.append(_P(content['lead'], bfont, 11.5, '#111827', sa=3))
    els.append(_P(content['recipient'], nfont, 27, theme['accent'], leading=32, sb=4, sa=4))
    els.append(HRFlowable(width='55%', thickness=0.8, color=_col(theme['gold'])))
    for p in (content.get('body') or []):
        els.append(_P(p, bfont, 11, '#1f2937', leading=16, sb=6))
    return els


# ===========================================================================
# layout archetypes — each a DIFFERENT structure
# ===========================================================================
def _lay_imperial(theme, content, avail=_AVAIL, width=L_W - 56 * mm):
    top = []
    lg = _logo()
    if lg is not None:
        top += [lg, Spacer(1, 3)]
    top += _kicker(content, theme) + [Spacer(1, 3), _title(content, theme, 27)]
    mid = _hero(content, theme)
    bot = [_details(content.get('fields'), theme, width, cols=3), Spacer(1, 8)] + _auth(content, theme, width)
    return _bands(top, mid, bot, avail, width, ratios=(0.28, 0.40, 0.32))


def _lay_sovereign(theme, content, avail=_AVAIL, width=L_W):
    # Left colour panel (crest + seal + serial) · right content
    primary = _col(theme['primary'])
    _h, bfont, _n = th.fonts(theme)
    lg = _logo(h=16, w=30)
    panel = [x for x in [lg, Spacer(1, 8), th.gold_seal(theme), Spacer(1, 8),
                         _P('S/N', bfont, 7, colors.white),
                         _P(content.get('serial') or '', bfont, 8, colors.white)] if x is not None]
    cw = 62 * mm
    rc = width - cw
    right_top = _kicker(content, theme) + [Spacer(1, 2), _title(content, theme, 23)]
    right_mid = _hero(content, theme)
    right_bot = [_details(content.get('fields'), theme, rc - 24 * mm, cols=2), Spacer(1, 6)] + \
        _auth(content, theme, rc - 24 * mm)
    right = _bands(right_top, right_mid, right_bot, avail, rc - 24 * mm,
                   ratios=(0.24, 0.42, 0.34))
    outer = Table([[panel, right]], colWidths=[cw, rc], rowHeights=[avail])
    outer.setStyle(TableStyle([('BACKGROUND', (0, 0), (0, 0), primary),
                               ('VALIGN', (0, 0), (0, 0), 'MIDDLE'), ('VALIGN', (1, 0), (1, 0), 'MIDDLE'),
                               ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                               ('LEFTPADDING', (1, 0), (1, 0), 14), ('RIGHTPADDING', (1, 0), (1, 0), 8),
                               ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
    return [outer]


def _lay_laureate(theme, content, avail=_AVAIL, width=L_W - 40 * mm):
    # Full-width reversed-out title band
    hfont, bfont, _n = th.fonts(theme)
    primary = _col(theme['primary'])
    band = Table([[_P(content['title'].upper(), hfont, 22, colors.white, leading=25)]], colWidths=[width])
    band.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), primary),
                              ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
    lg = _logo()
    top = ([lg] if lg is not None else []) + _kicker(content, theme) + [Spacer(1, 4), band]
    mid = _hero(content, theme)
    bot = [_details(content.get('fields'), theme, width, cols=3, boxed=True), Spacer(1, 8)] + _auth(content, theme, width)
    return _bands(top, mid, bot, avail, width, ratios=(0.28, 0.40, 0.32))


def _lay_regalia(theme, content, avail=_AVAIL, width=L_W - 44 * mm):
    # Split header:  SCHOOL  [crest]  (diploma feel), triple signatures
    hfont, bfont, _n = th.fonts(theme)
    lg = _logo(h=20, w=30)
    nm = _P(content['kicker'].upper(), hfont, 16, theme['primary'], leading=19)
    header = Table([[nm, lg or '']], colWidths=[width - 34 * mm, 34 * mm])
    header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'CENTER')]))
    top = [header, Spacer(1, 4), HRFlowable(width='100%', thickness=1.4, color=_col(theme['gold'])),
           Spacer(1, 6), _title(content, theme, 22)]
    mid = _hero(content, theme)
    sigs = dict(content); sigs['signatures'] = (content.get('signatures') or ['Principal', 'Registrar']) + ['Chairman']
    bot = [_details(content.get('fields'), theme, width, cols=3), Spacer(1, 8)] + _auth(sigs, theme, width)
    return _bands(top, mid, bot, avail, width, ratios=(0.30, 0.36, 0.34), halign='LEFT')


def _lay_meridian(theme, content, avail=_AVAIL, width=L_W):
    # Right medallion column
    _h, bfont, _n = th.fonts(theme)
    cw = 58 * mm
    lc = width - cw
    left_top = _kicker(content, theme) + [Spacer(1, 3), _title(content, theme, 24)]
    left_mid = _hero(content, theme)
    left_bot = [_details(content.get('fields'), theme, lc - 16 * mm, cols=2)]
    left = _bands(left_top, left_mid, left_bot, avail, lc - 16 * mm, ratios=(0.26, 0.42, 0.32), halign='LEFT')
    lg = _logo(h=16, w=30)
    col = [x for x in [lg, Spacer(1, 10), th.gold_seal(theme, dia=30), Spacer(1, 10),
                       th.rubber_stamp(theme, top=content.get('seal_text') or 'OFFICIAL', mid='SEAL', dia=26)]
           if x is not None]
    bc = th.barcode(content.get('serial'))
    if bc is not None:
        col += [Spacer(1, 8), bc]
    outer = Table([[left, col]], colWidths=[lc, cw], rowHeights=[avail])
    outer.setStyle(TableStyle([('VALIGN', (0, 0), (0, 0), 'MIDDLE'), ('VALIGN', (1, 0), (1, 0), 'MIDDLE'),
                               ('ALIGN', (1, 0), (1, 0), 'CENTER'),
                               ('LINEBEFORE', (1, 0), (1, 0), 0.8, _col(theme['gold'])),
                               ('LEFTPADDING', (1, 0), (1, 0), 10)]))
    return [outer]


def _lay_estate(theme, content, avail=_AVAIL, width=L_W - 60 * mm):
    hfont, bfont, _n = th.fonts(theme)
    lg = _logo()
    top = ([lg, Spacer(1, 4)] if lg is not None else []) + [_title(content, theme, 24)] + _kicker(content, theme)
    mid = _hero(content, theme) + [Spacer(1, 6),
          _details(content.get('fields'), theme, width - 30 * mm, cols=2, boxed=True)]
    bot = _auth(content, theme, width)
    return _bands(top, mid, bot, avail, width, ratios=(0.24, 0.50, 0.26))


def _lay_platinum(theme, content, avail=_AVAIL, width=L_W - 70 * mm):
    hfont, bfont, _n = th.fonts(theme)
    lg = _logo(h=13, w=34)
    top = ([lg, Spacer(1, 6)] if lg is not None else []) + [
        _P(content['kicker'].upper(), hfont, 11, theme['accent'], leading=14, sa=6),
        _P(content['title'].upper(), hfont, 21, theme['primary'], leading=24)]
    mid = _hero(content, theme)
    bot = [_details(content.get('fields'), theme, width, cols=3), Spacer(1, 10)] + _auth(content, theme, width)
    return _bands(top, mid, bot, avail, width, ratios=(0.30, 0.38, 0.32))


def _lay_verdant(theme, content, avail=_AVAIL, width=L_W - 50 * mm):
    hfont, bfont, _n = th.fonts(theme)
    lg = _logo()
    top = ([lg] if lg is not None else []) + _kicker(content, theme) + [
        Spacer(1, 2), _title(content, theme, 23),
        _P('★ ★ ★', bfont, 12, theme['gold'], sb=2)]
    mid = _hero(content, theme)
    bot = [_details(content.get('fields'), theme, width, cols=3), Spacer(1, 8)] + _auth(content, theme, width)
    return _bands(top, mid, bot, avail, width, ratios=(0.30, 0.40, 0.30))


def _lay_oxford(theme, content, avail=_AVAIL, width=L_W - 40 * mm):
    # Two-column middle: certifying text | details panel
    _h, bfont, _n = th.fonts(theme)
    lg = _logo()
    top = ([lg] if lg is not None else []) + _kicker(content, theme) + [Spacer(1, 3), _title(content, theme, 23)]
    body = _hero(content, theme)
    det = [th.section_bar('Candidate Details', theme, (width) * 0.42),
           _details(content.get('fields'), theme, (width) * 0.42, cols=1, boxed=True)]
    two = Table([[body, det]], colWidths=[width * 0.56, width * 0.44])
    two.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (1, 0), (1, 0), 10)]))
    bot = _auth(content, theme, width)
    return _bands(top, [two], bot, avail, width, ratios=(0.24, 0.50, 0.26))


def _lay_crown(theme, content, avail=_AVAIL, width=L_W - 56 * mm):
    hfont, bfont, _n = th.fonts(theme)
    top = [th.gold_seal(theme, dia=26), Spacer(1, 4)] + _kicker(content, theme) + [Spacer(1, 2), _title(content, theme, 24)]
    mid = _hero(content, theme)
    bot = [_details(content.get('fields'), theme, width, cols=3), Spacer(1, 8)] + _auth(content, theme, width)
    return _bands(top, mid, bot, avail, width, ratios=(0.30, 0.40, 0.30))


def _lay_chancellor(theme, content, avail=_AVAIL, width=L_W):
    # Left content bands · right signature/seal stack
    _h, bfont, _n = th.fonts(theme)
    cw = 56 * mm
    lc = width - cw
    lt = _kicker(content, theme) + [Spacer(1, 3), _title(content, theme, 23)]
    lm = _hero(content, theme)
    lb = [_details(content.get('fields'), theme, lc - 16 * mm, cols=2)]
    left = _bands(lt, lm, lb, avail, lc - 16 * mm, ratios=(0.24, 0.44, 0.32), halign='LEFT')
    labels = content.get('signatures') or ['Principal', 'Registrar']
    stack = [th.rubber_stamp(theme, top=content.get('seal_text') or 'OFFICIAL', mid='SEAL', dia=24), Spacer(1, 10)]
    for s in labels:
        stack += [_P('____________', bfont, 10, '#334155'), _P(f'<b>{s}</b>', bfont, 8.5, '#334155'), Spacer(1, 8)]
    stack += [th.gold_seal(theme)]
    outer = Table([[left, stack]], colWidths=[lc, cw], rowHeights=[avail])
    outer.setStyle(TableStyle([('VALIGN', (0, 0), (0, 0), 'MIDDLE'), ('VALIGN', (1, 0), (1, 0), 'MIDDLE'),
                               ('ALIGN', (1, 0), (1, 0), 'CENTER'),
                               ('LINEBEFORE', (1, 0), (1, 0), 0.8, _col(theme['gold'])),
                               ('LEFTPADDING', (1, 0), (1, 0), 10)]))
    return [outer]


# key -> {name, theme (collection key), fn}.  Every entry is a DIFFERENT layout
# function bound to a distinct palette — no two templates are alike.
LAYOUTS = {
    'imperial':   {'name': 'Imperial',   'theme': 'gold',           'fn': _lay_imperial},
    'sovereign':  {'name': 'Sovereign',  'theme': 'royal',          'fn': _lay_sovereign},
    'laureate':   {'name': 'Laureate',   'theme': 'classic',        'fn': _lay_laureate},
    'regalia':    {'name': 'Regalia',    'theme': 'british',        'fn': _lay_regalia},
    'meridian':   {'name': 'Meridian',   'theme': 'sapphire',       'fn': _lay_meridian},
    'estate':     {'name': 'Estate',     'theme': 'heritage',       'fn': _lay_estate},
    'platinum':   {'name': 'Platinum',   'theme': 'platinum',       'fn': _lay_platinum},
    'verdant':    {'name': 'Verdant',    'theme': 'green_heritage', 'fn': _lay_verdant},
    'oxford':     {'name': 'Oxford',     'theme': 'academic',       'fn': _lay_oxford},
    'crown':      {'name': 'Crown',      'theme': 'luxury',         'fn': _lay_crown},
    'chancellor': {'name': 'Chancellor', 'theme': 'executive',      'fn': _lay_chancellor},
}


def render(key, content):
    lay = LAYOUTS.get(key) or LAYOUTS['imperial']
    theme = th.resolve(lay['theme'], content.get('_branding'))
    return lay['fn'](theme, content)


def theme_key(key):
    return (LAYOUTS.get(key) or LAYOUTS['imperial'])['theme']
