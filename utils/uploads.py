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


# Default budget for stored images: keep them small enough to be cheap to store
# and fast to serve, without visibly hurting quality.
TARGET_BYTES = 600 * 1024
MAX_STORE_DIM = 1600


def encode_to_target(im, target_bytes=TARGET_BYTES, max_dim=MAX_STORE_DIM, min_quality=45):
    """Re-encode a PIL image to at most ``target_bytes`` while keeping quality as
    high as possible. Returns ``(bytes, mime)``.

    - Auto-orients (EXIF) and downscales the longest side to ``max_dim``.
    - Opaque images → progressive JPEG, stepping quality down (then downscaling
      if the floor quality is still too big) until the budget is met.
    - Images with transparency → PNG, downscaled until they fit (never flattened,
      so a logo/graphic keeps its alpha). A tiny PNG that can't be shrunk further
      is returned as-is even if slightly over budget.
    """
    from io import BytesIO
    from PIL import Image, ImageOps
    try:
        im = ImageOps.exif_transpose(im)
    except Exception:
        pass
    has_alpha = im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info)
    if max(im.size) > max_dim:
        im.thumbnail((max_dim, max_dim), Image.LANCZOS)

    if has_alpha:
        im = im.convert('RGBA')
        data = b''
        for _ in range(8):
            out = BytesIO()
            im.save(out, 'PNG', optimize=True)
            data = out.getvalue()
            if len(data) <= target_bytes or max(im.size) <= 480:
                return data, 'image/png'
            w, h = im.size
            im = im.resize((max(1, int(w * 0.85)), max(1, int(h * 0.85))), Image.LANCZOS)
        return data, 'image/png'

    im = im.convert('RGB')

    def _jpeg(image, q):
        out = BytesIO()
        image.save(out, 'JPEG', quality=q, optimize=True, progressive=True)
        return out.getvalue()

    for _ in range(6):
        data = None
        for q in (88, 82, 76, 70, 62, 54, min_quality):
            data = _jpeg(im, q)
            if len(data) <= target_bytes:
                return data, 'image/jpeg'
            if q == min_quality:
                break
        if max(im.size) <= 400:        # don't shrink into oblivion
            return data, 'image/jpeg'
        w, h = im.size
        im = im.resize((int(w * 0.85), int(h * 0.85)), Image.LANCZOS)
    return _jpeg(im, min_quality), 'image/jpeg'
