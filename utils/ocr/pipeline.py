"""Orchestrate the score-sheet OCR: preprocess → Tesseract tokens → table
reconstruction → post-processing/validation. Produces a reviewable extraction —
it NEVER writes to permanent scores.

``extract_table`` returns a dict with the reconstructed/validated grid plus a
plain ``{headers, rows}`` view (values only) for callers that already have a
review UI, and ``review_count``/``issues`` so the UI can highlight the few cells
that need a human.
"""
import logging

log = logging.getLogger('ocr.pipeline')


def available():
    from utils.ocr import tesseract_engine
    return tesseract_engine.available()


def _guess_name_col(headers):
    import re
    for i, h in enumerate(headers):
        n = re.sub(r'[^a-z]', '', str(h).lower())
        if n in ('studentname', 'name', 'student', 'fullname', 'surname'):
            return i
    return 0


def extract_table(image_bytes, expected_headers=None, config=None,
                  min_conf=0.6, max_scores=None, tokens=None):
    """Full pipeline. ``tokens`` may be supplied directly (for tests / a
    different engine), bypassing preprocessing + Tesseract. Returns None when
    Tesseract is unavailable and no tokens were supplied."""
    from utils.ocr import preprocess as pre
    from utils.ocr import tesseract_engine
    from utils.ocr.reconstruct import reconstruct
    from utils.ocr import postprocess as pp

    meta = {'engine': 'tesseract'}
    if tokens is None:
        if not tesseract_engine.available():
            return None
        proc, pmeta = pre.preprocess(image_bytes, config)
        meta['preprocess'] = pmeta
        image_width = (pmeta.get('proc_size') or pmeta.get('orig_size') or [None])[0]
        tokens = tesseract_engine.to_tokens(proc if proc is not None else image_bytes)
        if not tokens:
            return None
    else:
        image_width = None
        meta['engine'] = 'supplied'

    grid = reconstruct(tokens, expected_headers=expected_headers)
    if not grid['headers'] or not grid['rows']:
        return None
    name_col = _guess_name_col(grid['headers'])
    numeric_cols = [i for i in range(len(grid['headers'])) if i != name_col]
    max_by_idx = {}
    if max_scores:
        for i in numeric_cols:
            if i - 0 < len(max_scores):
                max_by_idx[i] = max_scores[i] if i < len(max_scores) else 100
    grid = pp.process(grid, name_col=name_col, numeric_cols=numeric_cols,
                      min_conf=min_conf, image_width=image_width, max_scores=max_by_idx or None)
    warnings = pp.consistency_check(grid, expected_ncol=len(expected_headers) if expected_headers else None)

    # Plain values view for the existing review flow.
    plain_rows = [[c.get('value') if c.get('value') is not None else '' for c in r['cells']]
                  for r in grid['rows']]
    # Per-cell review reasons keyed "r,c" so the template can highlight.
    flags = {}
    for ri, r in enumerate(grid['rows']):
        for ci, c in enumerate(r['cells']):
            if c.get('review_status') == pp.REVIEW or c.get('review_status') == pp.CORRECTED:
                flags['%d,%d' % (ri, ci)] = {'status': c['review_status'],
                                             'reasons': c.get('reasons', [])}
    log.info('ocr table: %d cols, %d rows, %d cells need review',
             len(grid['headers']), len(grid['rows']), grid.get('review_count', 0))
    return {'headers': grid['headers'],
            'rows': [[str(v) for v in row] for row in plain_rows],
            'name_col': name_col,
            'review_count': grid.get('review_count', 0),
            'cell_flags': flags,
            'warnings': warnings,
            'meta': meta,
            'grid': grid}
