"""Read a photographed / scanned broadsheet (many subjects, one total per cell)
into ``{'headers': [...], 'rows': [[...]]}`` — the same shape the Excel parser
returns — using the school's chosen OCR engine with fallback.

Claude vision returns the table as structured JSON (best for photos, handles
skew and handwriting); Tesseract goes through the geometry pipeline
(utils/ocr) that rebuilds rows/columns from word bounding boxes and validates
each cell. Whichever engine is chosen in Settings is tried first, then the other
if available.
"""


def ocr_table(image_bytes, mimetype='image/png'):
    """Best-effort table read. Returns ``{'headers','rows'}`` or None."""
    rich = ocr_table_rich(image_bytes, mimetype)
    return {'headers': rich['headers'], 'rows': rich['rows']} if rich else None


def ocr_table_rich(image_bytes, mimetype='image/png', expected_headers=None, max_scores=None):
    """Table read with cell-level review metadata when the engine supports it.

    Returns ``{'headers','rows','cell_flags','review_count','engine','warnings'}``
    or None. Tesseract goes through the modular reconstruction pipeline
    (bbox-based rows/columns + validation + per-cell review flags); Claude
    returns the table without per-cell flags."""
    from utils.ocr_engine import engine_order
    for eng in engine_order():
        out = None
        flags, review_count, warnings = {}, 0, []
        try:
            if eng == 'claude':
                from utils.waec_ocr import vision_extract_broadsheet
                out = vision_extract_broadsheet(image_bytes, mimetype or 'image/png')
            elif eng == 'tesseract':
                from utils.ocr.pipeline import extract_table
                res = extract_table(image_bytes, expected_headers=expected_headers,
                                    max_scores=max_scores)
                if res:
                    out = {'headers': res['headers'], 'rows': res['rows']}
                    flags = res.get('cell_flags', {})
                    review_count = res.get('review_count', 0)
                    warnings = res.get('warnings', [])
        except Exception:
            out = None
        if out and out.get('headers') and out.get('rows'):
            return {'headers': out['headers'], 'rows': out['rows'],
                    'cell_flags': flags, 'review_count': review_count,
                    'engine': eng, 'warnings': warnings}
    return None
