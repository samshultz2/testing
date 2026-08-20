"""Which OCR engine reads score sheets — Claude vision, Tesseract, or PaddleOCR.

The choice is a per-school setting (``ocr_engine``): ``auto`` (default) prefers
Claude vision when configured, else Tesseract; or a school can pin ``claude``,
``tesseract`` or ``paddle``. ``engine_order()`` turns that choice into the list
of engines to actually try, filtered to what is installed/available, so a scan
always has a working fallback.
"""

ENGINES = ('auto', 'claude', 'tesseract', 'paddle')
_DEFAULT = 'auto'


def selected_engine():
    """The configured engine id, defaulting to 'auto'."""
    try:
        from models import SchoolSettings
        v = (SchoolSettings.get('ocr_engine', '') or '').strip().lower()
        if v in ENGINES:
            return v
    except Exception:
        pass
    return _DEFAULT


def availability():
    """{engine: bool} for the three concrete engines."""
    from utils.waec_ocr import vision_available, tesseract_available
    from utils.paddle_ocr import paddle_available
    return {'claude': vision_available(),
            'tesseract': tesseract_available(),
            'paddle': paddle_available()}


def engine_order():
    """Ordered list of concrete engines to try for a scan, honouring the setting
    and dropping any that aren't available."""
    avail = availability()
    choice = selected_engine()
    if choice == 'auto':
        order = ['claude', 'tesseract', 'paddle']
    else:
        # Pinned engine first, then the others as fallback.
        order = [choice] + [e for e in ('claude', 'tesseract', 'paddle') if e != choice]
    return [e for e in order if avail.get(e)]


def status_rows():
    """UI-friendly per-engine status for the settings page."""
    avail = availability()
    labels = {'claude': 'Claude vision (handwriting, needs API key)',
              'tesseract': 'Tesseract (printed text, free, on-server)',
              'paddle': 'PaddleOCR + OpenCV (fast, cell-cropped digits)'}
    installed_hint = {
        'claude': 'Set an Anthropic key above to enable.',
        'tesseract': 'Install the tesseract-ocr system package + pytesseract.',
        'paddle': 'pip install paddleocr paddlepaddle opencv-python numpy on the server.'}
    return [{'id': e, 'label': labels[e], 'available': avail[e],
             'hint': '' if avail[e] else installed_hint[e]}
            for e in ('claude', 'tesseract', 'paddle')]
