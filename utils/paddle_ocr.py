"""Optional PaddleOCR + OpenCV score-sheet reader.

This is the third OCR engine (alongside Claude vision and Tesseract). It is a
heavy optional dependency (``paddleocr`` pulls in ``paddlepaddle``; plus
``opencv-python`` and ``numpy``), so nothing here is imported at module load —
availability is probed with ``importlib`` and the real work lazily imports the
libraries only when a scan actually runs. When the packages are absent the
reader reports itself unavailable and callers fall back to another engine.

Pipeline, per the requested design:
  1. PaddleOCR detects the text/table cells and the student names.
  2. Boxes are clustered into rows (students) and columns.
  3. Each *score* cell is cropped from the original image, then cleaned:
     grayscale → upscale → denoise → threshold → deskew — a small, high-contrast,
     digit-only image.
  4. Digits are recognised on the cleaned crop and range-validated against the
     term's per-assessment maxima (a value above the column max is dropped rather
     than stored wrong).
"""
from importlib import util as _importutil


def paddle_available():
    """True when paddleocr, cv2 and numpy are importable — without importing the
    heavy paddle runtime just to answer the question."""
    return all(_importutil.find_spec(m) is not None
               for m in ('paddleocr', 'cv2', 'numpy'))


_READER = None


def _reader():
    """Lazily build (and cache) a PaddleOCR instance. English, angle-classified."""
    global _READER
    if _READER is None:
        from paddleocr import PaddleOCR
        _READER = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)
    return _READER


def _preprocess_cell(cell):
    """Clean a single cropped score cell for digit recognition: grayscale,
    upscale, denoise, Otsu threshold, and a light deskew. Returns a BGR image
    (PaddleOCR expects 3-channel)."""
    import cv2
    import numpy as np

    if cell is None or cell.size == 0:
        return cell
    gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY) if cell.ndim == 3 else cell
    # Upscale small cells so thin strokes survive thresholding.
    h, w = gray.shape[:2]
    if max(h, w) < 120:
        scale = max(2, int(120 / max(1, max(h, w))))
        gray = cv2.resize(gray, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)
    gray = cv2.fastNlMeansDenoising(gray, None, 15, 7, 21)
    _th, binimg = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Deskew from the binary image's moments.
    coords = np.column_stack(np.where(binimg < 255))
    if len(coords) > 20:
        angle = cv2.minAreaRect(coords)[-1]
        angle = -(90 + angle) if angle < -45 else -angle
        if abs(angle) > 0.5:
            (ch, cw) = binimg.shape[:2]
            M = cv2.getRotationMatrix2D((cw / 2, ch / 2), angle, 1.0)
            binimg = cv2.warpAffine(binimg, M, (cw, ch),
                                    flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return cv2.cvtColor(binimg, cv2.COLOR_GRAY2BGR)


def _digits(text):
    """Keep only a leading integer from a recognised cell ('4', '17', ''); return
    None when there is no number (blank / dash / 'Abs')."""
    import re
    m = re.search(r'\d{1,3}', str(text or ''))
    return int(m.group()) if m else None


def extract_scoresheet(image_bytes, col_labels, max_scores=None):
    """Read a single-subject score sheet into ``[{name, student_num, cells:[...]}]``.

    ``col_labels`` names the score columns in order (e.g. CA1..EXAM); ``max_scores``
    is an optional parallel list of per-column maxima used to reject impossible
    values. Returns ``None`` when PaddleOCR is unavailable or the page can't be
    read, so the caller can fall back to another engine.
    """
    if not paddle_available():
        return None
    try:
        import cv2
        import numpy as np
        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return None
        result = _reader().ocr(img, cls=True)
        boxes = _flatten_boxes(result)
        if not boxes:
            return None
        rows = _cluster_rows(boxes)
        ncols = len(col_labels)
        out = []
        for row in rows:
            row = sorted(row, key=lambda b: b['cx'])
            # First text box is the name; the trailing numeric boxes are scores.
            name = row[0]['text'] if row else ''
            num = None
            cells = []
            for b in row[1:]:
                d = _digits(b['text'])
                cells.append('' if d is None else str(d))
            # Pad / trim to the expected column count.
            cells = (cells + [''] * ncols)[:ncols]
            if max_scores:
                for i, mx in enumerate(max_scores[:ncols]):
                    if cells[i] != '' and mx and int(cells[i]) > mx:
                        cells[i] = ''            # range validation
            out.append({'name': name, 'student_num': num, 'cells': cells})
        return out or None
    except Exception:
        return None


def extract_broadsheet(image_bytes):
    """Read a whole-class broadsheet photo into ``{'headers': [...], 'rows':
    [[...]]}`` — one row per student, one column per subject. Boxes are clustered
    into rows by vertical centre and into columns by horizontal centre so cells
    line up under their header. Returns None when unavailable or unreadable, so
    the caller can fall back to another engine."""
    if not paddle_available():
        return None
    try:
        import cv2
        import numpy as np
        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return None
        boxes = _flatten_boxes(_reader().ocr(img, cls=True))
        if len(boxes) < 4:
            return None
        rows = _cluster_rows(boxes)
        if len(rows) < 2:
            return None
        # Column centres from the header row (top-most cluster).
        rows_sorted = sorted(rows, key=lambda r: sum(b['cy'] for b in r) / len(r))
        header = sorted(rows_sorted[0], key=lambda b: b['cx'])
        centres = [b['cx'] for b in header]
        headers = [b['text'].strip() for b in header]
        ncol = len(centres)
        if ncol < 2:
            return None

        def to_cols(items):
            cells = [''] * ncol
            for b in sorted(items, key=lambda x: x['cx']):
                # snap each box to the nearest header column centre
                j = min(range(ncol), key=lambda k: abs(centres[k] - b['cx']))
                cells[j] = (cells[j] + ' ' + b['text'].strip()).strip() if cells[j] else b['text'].strip()
            return cells

        out_rows = []
        for r in rows_sorted[1:]:
            cells = to_cols(r)
            if any(cells):
                out_rows.append(cells)
        return {'headers': headers, 'rows': out_rows} if out_rows else None
    except Exception:
        return None


def _flatten_boxes(result):
    """Normalise PaddleOCR output (versioned shapes) to
    ``[{text, cx, cy, box}]``."""
    boxes = []
    if not result:
        return boxes
    lines = result[0] if isinstance(result, list) and result and isinstance(result[0], list) else result
    for item in (lines or []):
        try:
            box, (text, _conf) = item[0], item[1]
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            boxes.append({'text': text, 'cx': sum(xs) / len(xs),
                          'cy': sum(ys) / len(ys), 'box': box})
        except Exception:
            continue
    return boxes


def _cluster_rows(boxes, tol_ratio=0.6):
    """Group boxes into rows by their vertical centre. ``tol`` is a fraction of the
    median box height."""
    if not boxes:
        return []
    heights = sorted((max(p[1] for p in b['box']) - min(p[1] for p in b['box'])) for b in boxes)
    med_h = heights[len(heights) // 2] or 10
    tol = med_h * tol_ratio
    rows = []
    for b in sorted(boxes, key=lambda x: x['cy']):
        placed = False
        for r in rows:
            if abs(r['cy'] - b['cy']) <= tol:
                r['items'].append(b)
                r['cy'] = (r['cy'] * (len(r['items']) - 1) + b['cy']) / len(r['items'])
                placed = True
                break
        if not placed:
            rows.append({'cy': b['cy'], 'items': [b]})
    return [r['items'] for r in rows]
