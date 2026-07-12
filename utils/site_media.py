"""Upload processing for Website-Builder images.

Decode safely (shared decompression-bomb cap), auto-orient, downscale to a
web-sane size, and re-encode to a compact format — then store the bytes in the
school's own tenant DB (``SiteMedia``). Keeping images small (capped dimensions +
optimised encode) is what makes DB storage practical: a typical school-site image
lands at ~100–300 KB.
"""
from io import BytesIO

from utils.uploads import open_image, file_ext

ALLOWED_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024       # reject inputs larger than 8 MB
MAX_DIM = 1600                            # longest side after downscale (px)


def _measure(stream):
    stream.seek(0, 2)
    n = stream.tell()
    stream.seek(0)
    return n


def store_upload(file):
    """Validate + process an uploaded image and persist it as a ``SiteMedia`` row
    in the current tenant DB. Returns the row. Raises ``ValueError`` with a
    user-safe message on anything invalid."""
    from PIL import Image
    from models import db, SiteMedia

    if not file or not file.filename:
        raise ValueError('Choose an image file to upload.')
    ext = file_ext(file.filename)
    if ext not in ALLOWED_EXTS:
        raise ValueError('Image must be a PNG, JPG, WEBP or GIF.')
    stream = file.stream
    if _measure(stream) > MAX_UPLOAD_BYTES:
        raise ValueError('That image is too large (max 8 MB).')

    try:
        im = open_image(file)                       # bomb-safe decode
    except Exception:
        raise ValueError('That file is not a valid image.')

    # Respect camera orientation, then downscale the longest side.
    try:
        from PIL import ImageOps
        im = ImageOps.exif_transpose(im)
    except Exception:
        pass
    if max(im.size) > MAX_DIM:
        im.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)

    has_alpha = im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info)
    out = BytesIO()
    if has_alpha:
        im.convert('RGBA').save(out, 'PNG', optimize=True)
        mime = 'image/png'
    else:
        im.convert('RGB').save(out, 'JPEG', quality=82, optimize=True, progressive=True)
        mime = 'image/jpeg'
    raw = out.getvalue()

    row = SiteMedia(filename=(file.filename or 'image')[:160], mime=mime, data=raw,
                    width=im.width, height=im.height, bytes=len(raw))
    db.session.add(row)
    db.session.commit()
    return row
