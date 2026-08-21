"""Read a photographed / scanned broadsheet (many subjects, one total per cell)
into ``{'headers': [...], 'rows': [[...]]}`` — the same shape the Excel parser
returns — using the school's chosen OCR engine with fallback.

Claude vision returns the table as structured JSON (best for photos, handles
skew and handwriting); PaddleOCR clusters detected boxes into a grid; Tesseract
reconstructs columns from word positions. Whichever engine is chosen in Settings
is tried first, then the others that are installed.
"""


def ocr_table(image_bytes, mimetype='image/png'):
    """Best-effort table read. Returns ``{'headers','rows'}`` or None."""
    rich = ocr_table_rich(image_bytes, mimetype)
    return {'headers': rich['headers'], 'rows': rich['rows']} if rich else None


def ocr_table_rich(image_bytes, mimetype='image/png', expected_headers=None, max_scores=None):
    """Table read with cell-level review metadata when the engine supports it.

    Returns ``{'headers','rows','cell_flags','review_count','engine','warnings'}``
    or None. PaddleOCR goes through the modular reconstruction pipeline
    (bbox-based rows/columns + validation + per-cell review flags); Claude and
    Tesseract return the table without per-cell flags."""
    from utils.ocr_engine import engine_order
    for eng in engine_order():
        out = None
        flags, review_count, warnings = {}, 0, []
        try:
            if eng == 'claude':
                from utils.waec_ocr import vision_extract_broadsheet
                out = vision_extract_broadsheet(image_bytes, mimetype or 'image/png')
            elif eng == 'paddle':
                from utils.ocr.pipeline import extract_table
                res = extract_table(image_bytes, expected_headers=expected_headers,
                                    max_scores=max_scores)
                if res:
                    out = {'headers': res['headers'], 'rows': res['rows']}
                    flags = res.get('cell_flags', {})
                    review_count = res.get('review_count', 0)
                    warnings = res.get('warnings', [])
            elif eng == 'tesseract':
                out = _tesseract_table(image_bytes)
        except Exception:
            out = None
        if out and out.get('headers') and out.get('rows'):
            return {'headers': out['headers'], 'rows': out['rows'],
                    'cell_flags': flags, 'review_count': review_count,
                    'engine': eng, 'warnings': warnings}
    return None


def _tesseract_table(image_bytes):
    """Reconstruct a table from Tesseract word boxes: group words into lines, then
    snap each word to the nearest header-column x-centre."""
    try:
        import io
        import pytesseract
        from PIL import Image
    except Exception:
        return None
    try:
        img = Image.open(io.BytesIO(image_bytes))
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    except Exception:
        return None

    words = []
    n = len(data.get('text', []))
    for i in range(n):
        txt = (data['text'][i] or '').strip()
        if not txt or int(data.get('conf', ['-1'])[i] or -1) < 30:
            continue
        words.append({'text': txt, 'left': data['left'][i], 'top': data['top'][i],
                      'w': data['width'][i], 'h': data['height'][i],
                      'line': (data['block_num'][i], data['par_num'][i], data['line_num'][i])})
    if len(words) < 4:
        return None

    # Group into visual lines.
    lines = {}
    for w in words:
        lines.setdefault(w['line'], []).append(w)
    ordered = sorted(lines.values(), key=lambda ws: min(x['top'] for x in ws))
    if len(ordered) < 2:
        return None

    def cx(w):
        return w['left'] + w['w'] / 2

    header_words = sorted(ordered[0], key=lambda w: w['left'])
    centres = [cx(w) for w in header_words]
    headers = [w['text'] for w in header_words]
    ncol = len(centres)
    if ncol < 2:
        return None

    rows = []
    for ws in ordered[1:]:
        cells = [''] * ncol
        for w in sorted(ws, key=lambda x: x['left']):
            j = min(range(ncol), key=lambda k: abs(centres[k] - cx(w)))
            cells[j] = (cells[j] + ' ' + w['text']).strip() if cells[j] else w['text']
        if any(cells):
            rows.append(cells)
    return {'headers': headers, 'rows': rows} if rows else None
