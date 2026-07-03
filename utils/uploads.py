"""Shared file-upload validation helpers.

The app accepts uploads in a handful of routes (CBT question figures, the school
logo, OCR/scan images, and several in-memory spreadsheet/CSV imports). This
centralises the two checks those routes need so they stop re-implementing them:

- ``ext_ok`` — a case-insensitive extension whitelist that keys off the FINAL
  extension only, so a double-extension name (``evil.php.svg``) is judged by
  ``.svg`` and cannot sneak past.
- ``open_image`` — decode an uploaded image through Pillow with an explicit
  decompression-bomb cap (a spoofed/non-image file raises instead of being
  trusted on its name/Content-Type).

Persisted image uploads should re-encode the returned image (e.g. save as PNG)
so polyglots and embedded scripts (SVG) never reach disk.
"""
import os

# Cap decoded image dimensions (width*height). Mirrors utils/waec_ocr._MAX_IMAGE_PIXELS
# so every image path shares one decompression-bomb bound.
MAX_IMAGE_PIXELS = 50_000_000

# Common allow-lists (raster images only — deliberately NO '.svg', which can carry
# script and must never be stored/served from our own origin).
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
SCAN_EXTS = IMAGE_EXTS | {'.pdf'}


def file_ext(filename):
    """Lower-cased final extension of ``filename`` (incl. the dot), or ''."""
    return os.path.splitext(filename or '')[1].lower()


def ext_ok(filename, allowed):
    """True if ``filename``'s final extension is in ``allowed`` (case-insensitive).

    Only the last extension is considered, so ``evil.php.svg`` is judged by
    ``.svg`` — double-extension tricks can't widen the whitelist.
    """
    return file_ext(filename) in {e.lower() for e in allowed}


def open_image(source):
    """Decode an uploaded image via Pillow with a decompression-bomb cap.

    ``source`` may be a path, a file-like stream, or a Werkzeug ``FileStorage``
    (its ``.stream`` is used). Returns a loaded PIL ``Image``; raises on a
    non-image, a corrupt file, or an over-large (bomb) image — so callers can
    treat "opened successfully" as "this really is a safe raster image".
    """
    from PIL import Image
    # Explicit cap (Pillow's default is ~178 MP); raises DecompressionBombError
    # past 2x this. Set on every call so no import-order race can leave it high.
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    stream = getattr(source, 'stream', source)
    im = Image.open(stream)
    im.load()                     # force full decode now (catches truncated/bomb files)
    return im
