"""Configurable image preprocessing for score-sheet OCR.

Everything is lazy (OpenCV/NumPy imported only when a step runs) and defensive:
the ORIGINAL image bytes are always preserved; preprocessing returns a *separate*
processed image for OCR. Steps can be toggled through a config dict so a caller
can try a lighter or heavier profile without code changes.

Nothing here is aggressive by default — deskew + gentle denoise + optional
upscale — because over-processing a clean screenshot (like the reference sheet)
hurts more than it helps.
"""

DEFAULT_CONFIG = {
    'grayscale': True,
    'denoise': True,
    'deskew': True,
    'threshold': False,      # Otsu binarisation — helps photos, hurts clean scans
    'upscale_min_width': 1400,   # upscale only if narrower than this
    'perspective': False,    # 4-point warp for photographed sheets (best-effort)
    'max_width': 3000,       # never blow past this (memory guard on 8GB VPS)
}


def available():
    from importlib import util
    return util.find_spec('cv2') is not None and util.find_spec('numpy') is not None


def preprocess(image_bytes, config=None):
    """Return ``(processed_bgr_ndarray, meta)`` or ``(None, meta)`` when OpenCV
    isn't installed. ``meta`` records the dimensions and which steps ran, for
    logging."""
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    meta = {'steps': [], 'ok': False}
    if not available():
        meta['error'] = 'opencv_not_installed'
        return None, meta
    import cv2
    import numpy as np
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        meta['error'] = 'decode_failed'
        return None, meta
    meta['orig_size'] = [int(img.shape[1]), int(img.shape[0])]

    if cfg.get('perspective'):
        warped = _perspective(img, cv2, np)
        if warped is not None:
            img = warped
            meta['steps'].append('perspective')

    work = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if cfg.get('grayscale') else img
    if cfg.get('grayscale'):
        meta['steps'].append('grayscale')

    if cfg.get('denoise'):
        work = (cv2.fastNlMeansDenoising(work, None, 10, 7, 21) if work.ndim == 2
                else cv2.fastNlMeansDenoisingColored(work, None, 10, 10, 7, 21))
        meta['steps'].append('denoise')

    if cfg.get('deskew') and work.ndim == 2:
        work, angle = _deskew(work, cv2, np)
        if angle:
            meta['steps'].append('deskew')
            meta['deskew_angle'] = round(float(angle), 2)

    if cfg.get('threshold') and work.ndim == 2:
        work = cv2.threshold(work, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        meta['steps'].append('threshold')

    # Upscale small images so thin digits survive; cap for memory.
    h, w = work.shape[:2]
    target = cfg.get('upscale_min_width') or 0
    if target and w < target:
        scale = min(target / w, (cfg.get('max_width') or target) / w)
        if scale > 1.05:
            work = cv2.resize(work, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
            meta['steps'].append('upscale')

    if work.ndim == 2:                       # OCR wants 3-channel
        work = cv2.cvtColor(work, cv2.COLOR_GRAY2BGR)
    meta['proc_size'] = [int(work.shape[1]), int(work.shape[0])]
    meta['ok'] = True
    return work, meta


def _deskew(gray, cv2, np):
    inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(inv > 0))
    if len(coords) < 50:
        return gray, 0.0
    angle = cv2.minAreaRect(coords)[-1]
    angle = -(90 + angle) if angle < -45 else -angle
    if abs(angle) < 0.3:
        return gray, 0.0
    (h, w) = gray.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE), angle


def _perspective(img, cv2, np):
    """Best-effort 4-point deskew for a photographed sheet: find the largest
    quadrilateral contour and warp it flat. Returns None when no good quad."""
    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)
        cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:5]
        page_area = img.shape[0] * img.shape[1]
        for c in cnts:
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            if len(approx) == 4 and cv2.contourArea(approx) > 0.4 * page_area:
                return _warp(img, approx.reshape(4, 2), cv2, np)
    except Exception:
        return None
    return None


def _warp(img, pts, cv2, np):
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1)
    rect = np.array([pts[np.argmin(s)], pts[np.argmin(d)],
                     pts[np.argmax(s)], pts[np.argmax(d)]], dtype='float32')
    (tl, tr, br, bl) = rect
    W = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    H = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    if W < 10 or H < 10:
        return None
    dst = np.array([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]], dtype='float32')
    M = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(img, M, (W, H))
