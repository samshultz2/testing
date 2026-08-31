"""Pure-Python Code 128 (subset B) barcode renderer → inline SVG.

No third-party dependency and no raster step: the output is a self-contained
``<svg>`` string that embeds cleanly in a printable HTML label sheet (and so
survives a strict CSP — nothing external is fetched). Code 128-B covers the
printable ASCII range (space…~), which is all a product SKU / EAN / ISBN needs.

``code128_svg('12345')`` returns the SVG; ``encodable(data)`` reports whether a
string can be represented in subset B.
"""
from __future__ import annotations

# Bar/space module widths for each Code 128 symbol value (0…106). Every pattern
# is six alternating widths (bar, space, bar, space, bar, space) except the stop
# pattern (index 106), which carries the final terminating bar. This is the
# canonical Code 128 table.
_PATTERNS = [
    "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312",
    "132212", "221213", "221312", "231212", "112232", "122132", "122231", "113222",
    "123122", "123221", "223211", "221132", "221231", "213212", "223112", "312131",
    "311222", "321122", "321221", "312212", "322112", "322211", "212123", "212321",
    "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313",
    "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121",
    "313121", "211331", "231131", "213113", "213311", "213131", "311123", "311321",
    "331121", "312113", "312311", "332111", "314111", "221411", "431111", "111224",
    "111422", "121124", "121421", "141122", "141221", "112214", "112412", "122114",
    "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111",
    "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112",
    "421211", "212141", "214121", "412121", "111143", "111341", "131141", "114113",
    "114311", "411113", "411311", "113141", "114131", "311141", "411131", "211412",
    "211214", "211232", "2331112",
]

_START_B = 104
_STOP = 106


def encodable(data) -> bool:
    """True when every character of ``data`` is representable in Code 128-B."""
    s = str(data or '')
    return bool(s) and all(32 <= ord(ch) <= 126 for ch in s)


def _symbols(data: str):
    """The list of Code 128 symbol values for ``data``: start, payload, checksum,
    stop — with the modulo-103 check character."""
    codes = [_START_B] + [ord(ch) - 32 for ch in data]
    checksum = codes[0] + sum(i * v for i, v in enumerate(codes[1:], start=1))
    codes.append(checksum % 103)
    codes.append(_STOP)
    return codes


def code128_svg(data, *, module=2, height=54, quiet=10, human=True) -> str:
    """Render ``data`` as a Code 128-B barcode SVG string.

    module  – width in px of a single-width bar/space
    height  – bar height in px (the human-readable line adds a little below)
    quiet   – quiet-zone width in modules on each side (min 10 per the spec)
    human   – draw the encoded text under the bars
    """
    data = str(data)
    if not encodable(data):
        raise ValueError('Code 128-B can only encode printable ASCII')
    bars = []             # (x_in_modules, width_in_modules) for the dark bars
    x = quiet
    for sym in _symbols(data):
        pattern = _PATTERNS[sym]
        dark = True
        for w in pattern:
            w = int(w)
            if dark:
                bars.append((x, w))
            x += w
            dark = not dark
    total_modules = x + quiet
    width = total_modules * module
    text_h = 14 if human else 0
    svg_h = height + text_h
    rects = ''.join(
        f'<rect x="{bx * module}" y="0" width="{bw * module}" height="{height}"/>'
        for bx, bw in bars)
    from markupsafe import escape
    safe = escape(data)
    text = ''
    if human:
        text = (f'<text x="{width / 2}" y="{height + 11}" text-anchor="middle" '
                f'font-family="monospace" font-size="12" fill="#000">{safe}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{svg_h}" '
            f'viewBox="0 0 {width} {svg_h}" role="img" aria-label="Barcode {safe}">'
            f'<rect width="{width}" height="{svg_h}" fill="#fff"/>'
            f'<g fill="#000">{rects}</g>{text}</svg>')
