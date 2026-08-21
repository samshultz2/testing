"""PaddleOCR wrapped as a token producer for the table reconstructor.

Detection + recognition give every printed/handwritten fragment a bounding box,
text and confidence — exactly the geometry the reconstructor needs to rebuild
rows/columns. This keeps the heavy runtime lazy and tolerant of PaddleOCR API
differences across versions (the ``.ocr(img)`` result shape has changed between
2.6/2.7/3.x).
"""
from importlib import util as _util

_OCR = None


def available():
    return all(_util.find_spec(m) is not None for m in ('paddleocr', 'cv2', 'numpy'))


def _engine(lang='en'):
    global _OCR
    if _OCR is None:
        from paddleocr import PaddleOCR
        # Try the modern signature, fall back to the older one.
        try:
            _OCR = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
        except TypeError:
            _OCR = PaddleOCR(lang=lang)
    return _OCR


def to_tokens(image, lang='en'):
    """Run PaddleOCR and return ``[{'text','conf','box':[x1,y1,x2,y2]}]``.

    ``image`` may be raw bytes or a decoded BGR ndarray. Returns ``None`` when
    PaddleOCR isn't installed or the page can't be read."""
    if not available():
        return None
    try:
        import cv2
        import numpy as np
        if isinstance(image, (bytes, bytearray)):
            img = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        else:
            img = image
        if img is None:
            return None
        eng = _engine(lang)
        try:
            result = eng.ocr(img, cls=True)
        except TypeError:
            result = eng.ocr(img)
        return _flatten(result)
    except Exception:
        return None


def _flatten(result):
    """Normalise PaddleOCR's versioned output to a flat token list."""
    tokens = []
    if not result:
        return tokens
    # 2.x: [[ [box, (text, conf)], ... ]]   |  some builds drop the outer list.
    pages = result
    if isinstance(result, list) and result and isinstance(result[0], list) \
            and result[0] and isinstance(result[0][0], list):
        pages = result
    else:
        pages = [result]
    for page in pages:
        for item in (page or []):
            try:
                box = item[0]
                rec = item[1]
                text = rec[0] if isinstance(rec, (list, tuple)) else str(rec)
                conf = float(rec[1]) if isinstance(rec, (list, tuple)) and len(rec) > 1 else 1.0
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                tokens.append({'text': str(text).strip(), 'conf': conf,
                               'box': [min(xs), min(ys), max(xs), max(ys)]})
            except Exception:
                continue
    return tokens
