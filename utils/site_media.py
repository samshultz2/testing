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

    # Orient, downscale and compress to a ≤600 KB budget (keeps transparency as
    # PNG, photos as progressive JPEG) — one shared helper across all upload paths.
    from utils.uploads import encode_to_target
    raw, mime = encode_to_target(im, max_dim=MAX_DIM)
    # The helper downscales an internal copy, so read the final dimensions back
    # from the encoded bytes (not the original `im`).
    with Image.open(BytesIO(raw)) as _probe:
        out_w, out_h = _probe.size

    # Route the bytes to the configured backend (DB / filesystem / object store).
    from utils import media_storage
    storage, key = media_storage.store(raw, mime)
    row = SiteMedia(filename=(file.filename or 'image')[:160], mime=mime,
                    storage=storage, storage_key=key,
                    data=(raw if storage == 'db' else None),
                    width=out_w, height=out_h, bytes=len(raw))
    db.session.add(row)
    db.session.commit()
    return row
