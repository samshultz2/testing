"""Tesseract wrapped as a token producer for the table reconstructor.

``pytesseract.image_to_data`` gives every word a bounding box and a confidence —
exactly the geometry the reconstructor needs to rebuild rows/columns from
positions rather than reading order. Lazy imports; returns None when Tesseract
isn't installed."""


def available():
    from utils.waec_ocr import tesseract_available
    return tesseract_available()


def to_tokens(image, min_conf=25):
    """Run Tesseract and return ``[{'text','conf','box':[x1,y1,x2,y2]}]``.

    ``image`` may be raw bytes or a decoded ndarray (BGR/gray). Returns None when
    Tesseract isn't available or the page yields nothing."""
    if not available():
        return None
    try:
        import io
        import pytesseract
        from PIL import Image
        import numpy as np  # noqa: F401  (only used when image is an ndarray)

        if isinstance(image, (bytes, bytearray)):
            img = Image.open(io.BytesIO(image))
        elif hasattr(image, 'shape'):
            arr = image
            if getattr(arr, 'ndim', 2) == 3:
                arr = arr[:, :, ::-1]           # BGR (OpenCV) -> RGB for PIL
            img = Image.fromarray(arr)
        else:
            img = image
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    except Exception:
        return None

    tokens = []
    n = len(data.get('text', []))
    for i in range(n):
        txt = (data['text'][i] or '').strip()
        if not txt:
            continue
        try:
            conf = float(data['conf'][i])
        except (TypeError, ValueError):
            conf = -1.0
        if conf < min_conf:
            continue
        x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
        tokens.append({'text': txt, 'conf': max(conf, 0) / 100.0,
                       'box': [x, y, x + w, y + h]})
    return tokens or None
