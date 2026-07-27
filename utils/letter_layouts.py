"""Formal-letter **layout archetypes** — genuinely distinct structures.

Like :mod:`utils.cert_layouts`, each entry is a different composition
(letterhead treatment, bio-table placement, body flow, signature/seal block),
not a recolour. Each is bound to a distinct palette, and the signature block is
anchored toward the foot so the page fills without a large blank bottom.
"""
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, HRFlowable

from utils import doc_themes as th

P_W = th.P_W
_AVAIL = 263 * mm - 46 * mm            # portrait frame (margins 16/18) - footer reserve


def _col(v):
    return colors.HexColor(v) if isinstance(v, str) else v


def _P(text, font, size, color, align=TA_LEFT, leading=None, sa=0, sb=0):
    return Paragraph(str(text), ParagraphStyle(
        'x', fontName=font, fontSize=size, textColor=_col(color), alignment=align,
        leading=leading or size * 1.3, spaceAfter=sa, spaceBefore=sb))


def _logo(h=17, w=30):
    return th._logo(max_h=h, max_w=w)


def _measure(flowables, width):
    total = 0
    for f in (flowables or []):
        for meth in ('getSpaceBefore',):
            try:
                total += getattr(f, meth)()
            except Exception:
                pass
        try:
            total += f.wrap(width, 3000)[1]
        except Exception:
            pass
        try:
            total += f.getSpaceAfter()
        except Exception:
            pass
    return total


def _anchor(body, sig, avail=_AVAIL, width=P_W):
    """Body at the top, signature block anchored near the foot (fills the page)."""
    gap = max(0, avail - _measure(body, width) - _measure(sig, width))
    return list(body) + ([Spacer(1, gap)] if gap > 8 else []) + list(sig)


# --- shared building blocks -----------------------------------------------
def _meta_row(content, theme, width, align_right_date=True):
    _h, bfont, _n = th.fonts(theme)
    left = _P(f"<b>Ref:</b> {content.get('ref') or ''}", bfont, 10, '#334155')
    right = _P(f"<b>Date:</b> {content.get('date') or ''}", bfont, 10, '#334155',
               TA_RIGHT if align_right_date else TA_LEFT)
    t = Table([[left, right]], colWidths=[width / 2, width / 2])
    t.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    return t


def _title(content, theme, align=TA_CENTER, size=14):
    hfont, _b, _n = th.fonts(theme)
    return _P(content['title'].upper(), hfont, size, theme['primary'], align, sa=8, sb=2)


def _body(content, theme):
    _h, bfont, _n = th.fonts(theme)
    els = []
    if content.get('salutation'):
        els.append(_P(content['salutation'], bfont, 11, '#111827', TA_LEFT, sa=6))
    for p in (content.get('body') or []):
        els.append(_P(p, bfont, 11, '#1f2937', TA_JUSTIFY, leading=17, sa=8))
    if content.get('closing'):
        els.append(_P(content['closing'], bfont, 11, '#1f2937', TA_LEFT, sb=6))
    return els


def _sig(content, theme, width, seals=True, labels=None, align='spread'):
    _h, bfont, _n = th.fonts(theme)
    labels = labels or (content.get('signatures') or ['Principal', 'Registrar'])
    small = ParagraphStyle('s', fontName=bfont, fontSize=8.5, alignment=TA_CENTER, textColor=_col('#334155'))
    line = ParagraphStyle('l', fontName=bfont, fontSize=10.5, alignment=TA_CENTER)
    stamp = th.rubber_stamp(theme, top=content.get('seal_text') or 'OFFICIAL', mid='SEAL')
    seal = th.gold_seal(theme)
    n = len(labels)
    mid = [[Paragraph('______________', line) for _ in labels],
           [Paragraph(f'<b>{x}</b>', small) for x in labels]]
    midt = Table(mid, colWidths=[(width - 56 * mm) / n] * n)
    midt.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('TOPPADDING', (0, 1), (-1, 1), 1)]))
    cells = [[stamp if seals else '', midt, seal if seals else '']]
    t = Table(cells, colWidths=[28 * mm, width - 56 * mm, 28 * mm])
    t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
    out = [t]
    bc = th.barcode(content.get('serial'))
    if bc is not None:
        strip = Table([[bc, _P('Verify at ' + (content.get('verify') or 'the school portal') +
                               '   ·   S/N: ' + str(content.get('serial') or ''),
                               bfont, 8, theme['accent'], TA_LEFT)]],
                      colWidths=[80 * mm, width - 80 * mm])
        strip.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                                   ('LEFTPADDING', (1, 0), (1, 0), 8), ('TOPPADDING', (0, 0), (-1, -1), 5)]))
        out.append(strip)
    return out


def _head_centered(content, theme):
    hfont, bfont, _n = th.fonts(theme)
    school = content.get('school') or {}
    els = []
    lg = _logo(h=18, w=34)
    if lg is not None:
        lg.hAlign = 'CENTER'
        els.append(lg)
    els.append(_P(school.get('name') or 'School', hfont, 18, theme['primary'], TA_CENTER, leading=21))
    if content.get('motto'):
        els.append(_P(f"<i>{content['motto']}</i>", bfont, 8.5, theme['gold'], TA_CENTER))
    contact = ' · '.join([x for x in [school.get('address'), school.get('phone'),
                                       school.get('email'), school.get('website')] if x])
    if contact:
        els.append(_P(contact, bfont, 8.5, '#475569', TA_CENTER))
    els += [Spacer(1, 4), HRFlowable(width='100%', thickness=1.2, color=_col(theme['gold'])), Spacer(1, 6)]
    return els


def _head_left(content, theme, rule=True):
    hfont, bfont, _n = th.fonts(theme)
    school = content.get('school') or {}
    lg = _logo(h=18, w=30)
    text = [_P(school.get('name') or 'School', hfont, 17, theme['primary'], TA_LEFT, leading=20)]
    if content.get('motto'):
        text.append(_P(f"<i>{content['motto']}</i>", bfont, 8.5, theme['gold'], TA_LEFT))
    contact = [x for x in [school.get('address'), school.get('phone'),
                           school.get('email'), school.get('website')] if x]
    right = [_P(x, bfont, 8.5, '#475569', TA_RIGHT) for x in contact]
    row = Table([[[lg] + text if lg is not None else text, right]],
                colWidths=[P_W * 0.6, P_W * 0.4])
    row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
    out = [row]
    if rule:
        out += [Spacer(1, 4), HRFlowable(width='100%', thickness=1.1, color=_col(theme['gold'])), Spacer(1, 6)]
    return out


def _bio(content, theme, width, cols=1, boxed=True):
    ft = th.field_table(content.get('fields') or [], theme, width)
    return [ft, Spacer(1, 8)] if ft is not None else []


# ===========================================================================
# layout archetypes
# ===========================================================================
def _lay_formal(theme, content):
    body = _head_centered(content, theme) + [_meta_row(content, theme, P_W), Spacer(1, 6),
            _title(content, theme)] + _bio(content, theme, P_W) + _body(content, theme)
    return _anchor(body, _sig(content, theme, P_W))


def _lay_crested_left(theme, content):
    body = _head_left(content, theme) + [_meta_row(content, theme, P_W), Spacer(1, 4),
            _title(content, theme, TA_LEFT, 15)] + _body(content, theme)
    return _anchor(body, _sig(content, theme, P_W, labels=[(content.get('signatures') or ['Principal'])[0]]))


def _lay_band(theme, content):
    hfont, bfont, _n = th.fonts(theme)
    school = content.get('school') or {}
    lg = _logo(h=16, w=26)
    name = _P(school.get('name') or 'School', hfont, 17, colors.white, TA_LEFT, leading=20)
    contact = ' · '.join([x for x in [school.get('phone'), school.get('email'), school.get('website')] if x])
    sub = _P(contact, bfont, 8, '#e5e7eb', TA_LEFT)
    band = Table([[lg or '', [name, sub]]], colWidths=[26 * mm, P_W - 26 * mm])
    band.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), _col(theme['primary'])),
                              ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                              ('LEFTPADDING', (0, 0), (0, 0), 8), ('TOPPADDING', (0, 0), (-1, -1), 8),
                              ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
    body = [band, Spacer(1, 8), _meta_row(content, theme, P_W), Spacer(1, 4),
            _title(content, theme)] + _bio(content, theme, P_W) + _body(content, theme)
    return _anchor(body, _sig(content, theme, P_W))


def _lay_side_accent(theme, content):
    w = P_W - 12 * mm                     # clear the left colour bar
    body = _head_left(content, theme) + [_meta_row(content, theme, w), Spacer(1, 4),
            _title(content, theme, TA_LEFT, 15)] + _body(content, theme)
    sig = _sig(content, theme, w)
    inner = _anchor(body, sig)
    outer = Table([['', inner]], colWidths=[12 * mm, w])
    outer.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    return [outer]


def _lay_memo(theme, content):
    hfont, bfont, _n = th.fonts(theme)
    school = content.get('school') or {}
    body = [_P(school.get('name') or 'School', hfont, 22, theme['primary'], TA_LEFT, leading=24),
            HRFlowable(width='100%', thickness=1.4, color=_col(theme['primary'])), Spacer(1, 6),
            _meta_row(content, theme, P_W), Spacer(1, 4),
            _P(content['title'].upper(), hfont, 12, theme['accent'], TA_LEFT, sa=8)] + _body(content, theme)
    sig = _sig(content, theme, P_W, seals=False)
    contact = ' · '.join([x for x in [school.get('address'), school.get('phone'),
                                      school.get('email'), school.get('website')] if x])
    sig = sig + [Spacer(1, 6), HRFlowable(width='100%', thickness=0.5, color=_col(theme['gold'])),
                 _P(contact, bfont, 7.5, '#64748b', TA_CENTER)]
    return _anchor(body, sig)


def _lay_deed(theme, content):
    body = _head_centered(content, theme) + [_title(content, theme), _meta_row(content, theme, P_W),
            Spacer(1, 6)] + _bio(content, theme, P_W) + _body(content, theme)
    return _anchor(body, _sig(content, theme, P_W,
                              labels=(content.get('signatures') or ['Principal', 'Registrar'])))


def _lay_reference_card(theme, content):
    # bio table boxed beside the salutation; premium reference-letter feel
    body = _head_left(content, theme) + [_title(content, theme), _meta_row(content, theme, P_W), Spacer(1, 6)]
    if content.get('salutation'):
        body.append(_P(content['salutation'], th.fonts(theme)[1], 11, '#111827', TA_LEFT, sa=6))
    body += _bio(content, theme, P_W)
    for p in (content.get('body') or []):
        body.append(_P(p, th.fonts(theme)[1], 11, '#1f2937', TA_JUSTIFY, leading=17, sa=8))
    if content.get('closing'):
        body.append(_P(content['closing'], th.fonts(theme)[1], 11, '#1f2937', TA_LEFT, sb=6))
    return _anchor(body, _sig(content, theme, P_W))


def _lay_panel_left(theme, content):
    _h, bfont, _n = th.fonts(theme)
    cw, rc = 46 * mm, P_W - 46 * mm
    lg = _logo(h=16, w=28)
    panel = [x for x in [lg, Spacer(1, 10), th.gold_seal(theme), Spacer(1, 10),
                         _P('REF', bfont, 7, colors.white, TA_CENTER),
                         _P(content.get('ref') or '', bfont, 7.5, colors.white, TA_CENTER)] if x is not None]
    school = content.get('school') or {}
    right_head = [_P(school.get('name') or 'School', th.fonts(theme)[0], 16, theme['primary'], TA_LEFT, leading=19)]
    if content.get('motto'):
        right_head.append(_P(f"<i>{content['motto']}</i>", bfont, 8.5, theme['gold'], TA_LEFT))
    right_head += [Spacer(1, 4), HRFlowable(width='100%', thickness=1, color=_col(theme['gold'])), Spacer(1, 6),
                   _title(content, theme, TA_LEFT, 14)]
    right_body = right_head + _bio(content, theme, rc - 16 * mm) + _body(content, theme)
    right = _anchor(right_body, _sig(content, theme, rc - 16 * mm), avail=_AVAIL, width=rc - 16 * mm)
    outer = Table([[panel, right]], colWidths=[cw, rc], rowHeights=[_AVAIL])
    outer.setStyle(TableStyle([('BACKGROUND', (0, 0), (0, 0), _col(theme['primary'])),
                               ('VALIGN', (0, 0), (0, 0), 'MIDDLE'), ('VALIGN', (1, 0), (1, 0), 'TOP'),
                               ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                               ('LEFTPADDING', (1, 0), (1, 0), 12), ('TOPPADDING', (0, 0), (-1, -1), 8),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
    return [outer]


def _lay_contact_bar(theme, content):
    hfont, bfont, _n = th.fonts(theme)
    school = content.get('school') or {}
    head = _head_left(content, theme, rule=False)
    contact = ' · '.join([x for x in [school.get('phone'), school.get('email'), school.get('website')] if x])
    bar = Table([[_P(contact, bfont, 8.5, colors.white, TA_CENTER)]], colWidths=[P_W])
    bar.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), _col(theme['accent'])),
                             ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
    body = head + [bar, Spacer(1, 8), _meta_row(content, theme, P_W), Spacer(1, 4),
                   _title(content, theme)] + _bio(content, theme, P_W) + _body(content, theme)
    return _anchor(body, _sig(content, theme, P_W))


def _lay_registrar(theme, content):
    hfont, bfont, _n = th.fonts(theme)
    body = _head_centered(content, theme) + [
        _P('OFFICE OF THE REGISTRAR', hfont, 10, theme['accent'], TA_CENTER, sa=2),
        _title(content, theme), _meta_row(content, theme, P_W), Spacer(1, 6)]
    body += _bio(content, theme, P_W) + _body(content, theme)
    return _anchor(body, _sig(content, theme, P_W, labels=['Registrar', 'Principal']))


LAYOUTS = {
    'formal':     {'name': 'Formal',        'theme': 'classic',      'fn': _lay_formal,         'style': 'frame'},
    'crested':    {'name': 'Crested Left',  'theme': 'executive',    'fn': _lay_crested_left,   'style': 'plain'},
    'banner':     {'name': 'Banner',        'theme': 'corporate',    'fn': _lay_band,           'style': 'plain'},
    'accent':     {'name': 'Side Accent',   'theme': 'academic',     'fn': _lay_side_accent,    'style': 'sidebar'},
    'memo':       {'name': 'Memo',          'theme': 'minimalist',   'fn': _lay_memo,           'style': 'plain'},
    'deed':       {'name': 'Deed',          'theme': 'heritage',     'fn': _lay_deed,           'style': 'frame'},
    'reference':  {'name': 'Reference',     'theme': 'premium',      'fn': _lay_reference_card, 'style': 'frame'},
    'panel':      {'name': 'Panel',         'theme': 'royal',        'fn': _lay_panel_left,     'style': 'plain'},
    'contactbar': {'name': 'Contact Bar',   'theme': 'contemporary', 'fn': _lay_contact_bar,    'style': 'band'},
    'registry':   {'name': 'Registry',      'theme': 'sapphire',     'fn': _lay_registrar,      'style': 'frame'},
}


def render(key, content):
    lay = LAYOUTS.get(key) or LAYOUTS['formal']
    theme = th.resolve(lay['theme'], content.get('_branding'))
    return lay['fn'](theme, content)


def theme_key(key):
    return (LAYOUTS.get(key) or LAYOUTS['formal'])['theme']


def decorator_style(key):
    return (LAYOUTS.get(key) or LAYOUTS['formal']).get('style', 'frame')
