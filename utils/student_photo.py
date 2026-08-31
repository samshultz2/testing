"""Student passport-photo storage.

Photos are personal data, so they live in the school's own tenant DB (durable
across restarts) in the dedicated ``StudentPhoto`` table and are only ever served
behind login + branch scope — never through the public site-media route. Uploads
are decoded bomb-safely, auto-oriented, cropped to a passport (portrait) ratio,
downscaled and re-encoded small (a passport photo needs little detail), so a row
is typically 20–60 KB.
"""
import base64
from io import BytesIO

from utils.uploads import open_image

MAX_INPUT_BYTES = 8 * 1024 * 1024        # reject raw inputs above 8 MB
TARGET_W, TARGET_H = 480, 600            # portrait passport crop (4:5), px


def _process(raw):
    """(out_bytes, mime, w, h) — oriented, centre-cropped to portrait, downscaled
    and re-encoded. Raises ValueError on anything that is not a safe image."""
    from PIL import Image, ImageOps
    if not raw:
        raise ValueError('No image data.')
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError('That image is too large (max 8 MB).')
    try:
        im = open_image(BytesIO(raw))
    except Exception:
        raise ValueError('That file is not a valid image.')
    try:
        im = ImageOps.exif_transpose(im)
    except Exception:
        pass
    # Centre-crop to the passport ratio, then fit to the target box.
    im = ImageOps.fit(im.convert('RGB'), (TARGET_W, TARGET_H), Image.LANCZOS, centering=(0.5, 0.4))
    out = BytesIO()
    im.save(out, 'JPEG', quality=85, optimize=True, progressive=True)
    return out.getvalue(), 'image/jpeg', im.width, im.height


def save_bytes(student, raw):
    """Store (or replace) a student's photo from raw image bytes. Returns the row."""
    from models import db, StudentPhoto
    data, mime, w, h = _process(raw)
    row = StudentPhoto.query.filter_by(student_id=student.id).first()
    if row is None:
        row = StudentPhoto(student_id=student.id)
        db.session.add(row)
    row.data, row.mime, row.width, row.height, row.bytes = data, mime, w, h, len(data)
    student.photo_url = served_url(student)
    return row


def save_data_url(student, data_url):
    """Store a photo supplied as a ``data:image/...;base64,...`` URL (how the
    student form submits it). Returns the row."""
    try:
        header, b64 = (data_url or '').split(',', 1)
    except ValueError:
        raise ValueError('Invalid image data.')
    if 'base64' not in header:
        raise ValueError('Invalid image data.')
    try:
        raw = base64.b64decode(b64)
    except Exception:
        raise ValueError('Invalid image data.')
    return save_bytes(student, raw)


def delete(student):
    """Remove a student's photo (and clear the pointer). Safe if none exists."""
    from models import db, StudentPhoto
    StudentPhoto.query.filter_by(student_id=student.id).delete()
    if (student.photo_url or '').startswith('/') or '/photo' in (student.photo_url or ''):
        student.photo_url = None


def served_url(student):
    try:
        from flask import url_for
        return url_for('main.student_photo', student_id=student.id)
    except Exception:
        return f'/students/{student.id}/photo'


def apply_from_form(student, value):
    """Apply the ``photo`` field submitted by the student form:
    - a ``data:`` URL → store the new photo;
    - an empty string → remove any existing photo;
    - anything else (e.g. the current served URL) → leave unchanged.
    Returns True if a change was made."""
    v = (value or '')
    if v.startswith('data:'):
        save_data_url(student, v)
        return True
    if v == '':
        # Only clear when the student actually had one, so an omitted field on a
        # partial update never wipes the photo.
        from models import StudentPhoto
        if StudentPhoto.query.filter_by(student_id=student.id).first():
            delete(student)
            return True
    return False


def photo_reader(student):
    """A reportlab ``ImageReader`` of the student's photo (for the ID card / docs),
    or None. Loads the bytes straight from the DB — no HTTP round-trip."""
    try:
        from models import StudentPhoto
        row = StudentPhoto.query.filter_by(student_id=student.id).first()
        if row is None or not row.data:
            return None
        from reportlab.lib.utils import ImageReader
        return ImageReader(BytesIO(row.data))
    except Exception:
        return None


def has_photo(student):
    try:
        from models import StudentPhoto
        return StudentPhoto.query.filter_by(student_id=student.id).first() is not None
    except Exception:
        return False
