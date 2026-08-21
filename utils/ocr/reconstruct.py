"""Reconstruct a table (rows × columns × cells) from OCR *tokens*.

A token is a dict ``{'text': str, 'conf': float, 'box': [x1,y1,x2,y2]}``. This
module never looks at pixels — it works purely from the token geometry, so it is
fully unit-testable. The output preserves, per cell, the source text, the mean
confidence, the bounding box, and a ``structure_conf`` describing how cleanly the
token fell inside its column — plus flags for the alignment problems the caller
must surface (a cell that straddles two columns, a row with the wrong cell
count, etc.).

Design goals (from the score-sheet import spec):
  * columns are established from the header row's horizontal positions, and every
    later token is assigned to the column whose x-range contains its centre —
    NEVER by OCR reading order;
  * rows are grouped by vertical position;
  * a value is never silently dropped or duplicated across columns.
"""


def _cx(box):
    return (box[0] + box[2]) / 2.0


def _cy(box):
    return (box[1] + box[3]) / 2.0


def _h(box):
    return abs(box[3] - box[1])


def cluster_rows(tokens, tol_ratio=0.6):
    """Group tokens into visual rows by their vertical centre. ``tol`` is a
    fraction of the median token height. Rows are returned top-to-bottom, tokens
    left-to-right."""
    toks = [t for t in tokens if t.get('box')]
    if not toks:
        return []
    heights = sorted(_h(t['box']) for t in toks)
    med_h = heights[len(heights) // 2] or 10
    tol = med_h * tol_ratio
    rows = []
    for t in sorted(toks, key=lambda x: _cy(x['box'])):
        cy = _cy(t['box'])
        placed = False
        for r in rows:
            if abs(r['cy'] - cy) <= tol:
                r['items'].append(t)
                r['cy'] = (r['cy'] * (len(r['items']) - 1) + cy) / len(r['items'])
                placed = True
                break
        if not placed:
            rows.append({'cy': cy, 'items': [t]})
    for r in rows:
        r['items'].sort(key=lambda x: _cx(x['box']))
    return [r['items'] for r in rows]


def _match_header_row(rows, expected_headers):
    """Index of the row that best matches the expected header labels (case/space
    -insensitive substring overlap); falls back to the first row."""
    if not expected_headers or not rows:
        return 0
    want = [_norm(h) for h in expected_headers]

    def score(row):
        texts = [_norm(t['text']) for t in row]
        hit = 0
        for w in want:
            if any(w and (w in tx or tx in w) for tx in texts):
                hit += 1
        return hit
    best_i, best = 0, -1
    for i, row in enumerate(rows[:5]):        # header is near the top
        s = score(row)
        if s > best:
            best, best_i = s, i
    return best_i


def _norm(s):
    import re
    return re.sub(r'[^a-z0-9]', '', str(s or '').lower())


def build_columns(header_row):
    """From the header tokens, return ``(labels, centres, bounds)`` where bounds
    are the x-cut points between adjacent columns (midpoints of the centres)."""
    header_row = sorted(header_row, key=lambda t: _cx(t['box']))
    labels = [t['text'].strip() for t in header_row]
    centres = [_cx(t['box']) for t in header_row]
    bounds = []
    for i in range(len(centres) - 1):
        bounds.append((centres[i] + centres[i + 1]) / 2.0)
    return labels, centres, bounds


def _assign_column(cx, centres, bounds):
    """Column index whose x-range contains ``cx`` (bounds are the cut points)."""
    for i, b in enumerate(bounds):
        if cx < b:
            return i
    return len(centres) - 1


def reconstruct(tokens, expected_headers=None):
    """Reconstruct the table. Returns::

        {'headers': [str, ...],
         'header_boxes': [[x1,y1,x2,y2], ...],
         'rows': [{'cells': [cell, ...], 'row_conf': float, 'flags': [str]}]}

    where each ``cell`` is
    ``{'text', 'conf', 'box', 'structure_conf', 'tokens': int, 'flags': [str]}``.
    An empty cell has ``text=''`` and ``tokens=0``.
    """
    rows = cluster_rows(tokens)
    if not rows:
        return {'headers': [], 'header_boxes': [], 'rows': []}
    hidx = _match_header_row(rows, expected_headers)
    header_row = rows[hidx]
    labels, centres, bounds = build_columns(header_row)
    ncol = len(centres)
    out_rows = []
    for ri, row in enumerate(rows):
        if ri == hidx:
            continue
        # Bucket tokens into columns by centre-x.
        buckets = [[] for _ in range(ncol)]
        for t in row:
            j = _assign_column(_cx(t['box']), centres, bounds)
            buckets[j].append(t)
        cells = []
        row_flags = []
        confs = []
        for j, bucket in enumerate(buckets):
            if not bucket:
                cells.append({'text': '', 'conf': None, 'box': None,
                              'structure_conf': 1.0, 'tokens': 0, 'flags': []})
                continue
            bucket.sort(key=lambda t: _cx(t['box']))
            text = ' '.join(t['text'].strip() for t in bucket).strip()
            conf = sum(float(t.get('conf', 0) or 0) for t in bucket) / len(bucket)
            xs = [t['box'][0] for t in bucket] + [t['box'][2] for t in bucket]
            ys = [t['box'][1] for t in bucket] + [t['box'][3] for t in bucket]
            box = [min(xs), min(ys), max(xs), max(ys)]
            flags = []
            # How centred is the merged token in its column? (structure quality)
            if j < len(centres):
                half = _column_half_width(j, centres, bounds)
                off = abs(_cx(box) - centres[j]) / half if half else 0
                structure_conf = max(0.0, 1.0 - min(off, 1.0))
            else:
                structure_conf = 1.0
            if len(bucket) > 1 and j != 0:
                flags.append('multi_token')       # >1 token in a (non-name) cell
            if structure_conf < 0.4:
                flags.append('offset')            # token sits far from column centre
            confs.append(conf)
            cells.append({'text': text, 'conf': conf, 'box': box,
                          'structure_conf': round(structure_conf, 3),
                          'tokens': len(bucket), 'flags': flags})
        filled = sum(1 for c in cells if c['tokens'])
        if filled == 0:
            continue                              # a blank separator line
        if filled < 2:
            row_flags.append('sparse_row')
        out_rows.append({'cells': cells,
                         'row_conf': round(sum(confs) / len(confs), 3) if confs else 0.0,
                         'flags': row_flags})
    return {'headers': labels,
            'header_boxes': [t['box'] for t in sorted(header_row, key=lambda t: _cx(t['box']))],
            'rows': out_rows}


def _column_half_width(j, centres, bounds):
    left = bounds[j - 1] if j - 1 >= 0 else centres[j] - (bounds[0] - centres[0] if bounds else 40)
    right = bounds[j] if j < len(bounds) else centres[j] + (centres[j] - bounds[-1] if bounds else 40)
    return max((right - left) / 2.0, 1.0)
