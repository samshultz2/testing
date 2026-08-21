"""Post-processing and validation of a reconstructed OCR table.

Turns raw cell text into a validated, review-annotated grid WITHOUT ever
inventing a value. Numeric cells are conservatively normalised (0 kept distinct
from empty; obvious OCR letter-lookalikes corrected but flagged); name cells are
preserved as read. Every cell gets a ``review_status`` and, when it needs a
human, the reasons why — so the preview can highlight exactly the few cells that
matter.
"""
import re

# review_status values
EMPTY = 'EMPTY'
OK = 'AUTO_ACCEPTABLE'
REVIEW = 'REVIEW_REQUIRED'
CORRECTED = 'CORRECTED'          # normalised but still worth a glance

# Conservative digit look-alike map used ONLY to rescue an otherwise-numeric cell.
_LOOKALIKE = {'O': '0', 'o': '0', 'Q': '0', 'D': '0',
              'l': '1', 'I': '1', '|': '1', 'i': '1',
              'S': '5', 's': '5', 'B': '8', 'Z': '2', 'z': '2', 'g': '9'}
_BLANKS = {'', '-', '--', '–', '—', '.', '_', 'nil', 'abs', 'absent', 'x', 'na', 'n/a'}


def normalize_score(text, max_score=100):
    """Return ``(value_or_None, status, reasons)`` for a numeric cell.

    * blank / dash / 'abs' → ``(None, EMPTY, [])``
    * clean integer in range → ``(int, OK, [])``
    * rescued from look-alikes (e.g. 'IOO'→100) → ``(int, CORRECTED, ['normalized'])``
    * out of range or unparseable → ``(value_or_None, REVIEW, [...])``
    """
    raw = str(text or '').strip()
    low = raw.lower()
    if low in _BLANKS:
        return None, EMPTY, []
    # A clean integer (optionally with stray surrounding punctuation).
    m = re.fullmatch(r'\s*(\d{1,3})\s*', raw)
    if m:
        v = int(m.group(1))
        if 0 <= v <= max_score:
            return v, OK, []
        return v, REVIEW, ['out_of_range']
    # Try to rescue a mostly-numeric token by mapping look-alikes.
    mapped = ''.join(_LOOKALIKE.get(ch, ch) for ch in raw)
    m2 = re.fullmatch(r'\s*(\d{1,3})\s*', mapped)
    if m2:
        v = int(m2.group(1))
        reasons = ['normalized']
        if not (0 <= v <= max_score):
            return v, REVIEW, reasons + ['out_of_range']
        return v, CORRECTED, reasons          # e.g. IOO -> 100, needs a glance
    # Digits buried in noise → ambiguous, do NOT guess.
    if re.search(r'\d', raw):
        return None, REVIEW, ['ambiguous']
    return None, REVIEW, ['not_a_number']


def clean_name(text):
    """Trim + collapse whitespace only. Names are preserved as OCR read them —
    never auto-corrected."""
    return re.sub(r'\s+', ' ', str(text or '').strip())


def process(grid, name_col, numeric_cols, min_conf=0.6, image_width=None,
            max_scores=None):
    """Annotate a reconstructed ``grid`` (from reconstruct.reconstruct).

    ``name_col`` is the header index of the student-name column; ``numeric_cols``
    the set/list of header indices that hold scores; ``max_scores`` optional
    per-column maxima (index→max). Returns the grid with each cell gaining
    ``value``, ``review_status`` and ``reasons`` keys, plus a top-level
    ``review_count`` and ``issues`` list of ``(row, col)``.
    """
    numeric = set(numeric_cols or [])
    maxes = max_scores or {}
    issues = []
    for ri, row in enumerate(grid.get('rows', [])):
        for ci, cell in enumerate(row['cells']):
            conf = cell.get('conf')
            low_conf = (conf is not None and conf < min_conf)
            if ci == name_col:
                cell['value'] = clean_name(cell.get('text', ''))
                reasons = []
                if not cell['value']:
                    reasons.append('missing_name')
                if low_conf:
                    reasons.append('low_confidence')
                # A name whose box starts hard against the left edge may be cropped.
                if image_width and cell.get('box') and cell['box'][0] <= image_width * 0.01:
                    reasons.append('possibly_cropped')
                cell['review_status'] = REVIEW if reasons else OK
                cell['reasons'] = reasons
            elif ci in numeric:
                value, status, reasons = normalize_score(
                    cell.get('text', ''), maxes.get(ci, 100))
                cell['value'] = value
                if low_conf and status in (OK, CORRECTED):
                    status = REVIEW
                    reasons = reasons + ['low_confidence']
                for f in cell.get('flags', []):          # structural doubts
                    if f in ('multi_token', 'offset') and status in (OK, CORRECTED):
                        status = REVIEW
                    if f not in reasons:
                        reasons.append(f)
                cell['review_status'] = status
                cell['reasons'] = reasons
            else:
                cell['value'] = (cell.get('text') or '').strip()
                cell['review_status'] = EMPTY if not cell['value'] else OK
                cell['reasons'] = []
            if cell['review_status'] == REVIEW:
                issues.append((ri, ci))
        # Whole-row structural doubt.
        if 'sparse_row' in row.get('flags', []):
            row['review'] = True
    grid['review_count'] = len(issues)
    grid['issues'] = issues
    return grid


def consistency_check(grid, expected_ncol=None):
    """Table-level checks; returns a list of human-readable warnings."""
    warns = []
    headers = grid.get('headers', [])
    if expected_ncol and len(headers) != expected_ncol:
        warns.append(f'Detected {len(headers)} columns, expected {expected_ncol}.')
    ncol = len(headers)
    for ri, row in enumerate(grid.get('rows', [])):
        if len(row['cells']) != ncol:
            warns.append(f'Row {ri + 1} has {len(row["cells"])} cells, expected {ncol}.')
    return warns
