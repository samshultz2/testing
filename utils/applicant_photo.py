"""Applicant passport-photo storage, mirroring utils/student_photo.py but for
the admissions pipeline. Reuses the same image processing (orient, centre-crop
to passport ratio, downscale, re-encode as JPEG)."""
import base64

from utils.student_photo import _process   # oriented/cropped/downscaled bytes


def save_bytes(applicant, raw):
    """Store (or replace) an applicant's photo from raw image bytes."""
    from models import db, ApplicantPhoto
    data, mime, w, h = _process(raw)
    row = ApplicantPhoto.query.filter_by(applicant_id=applicant.id).first()
    if row is None:
        row = ApplicantPhoto(applicant_id=applicant.id)
        db.session.add(row)
    row.data, row.mime, row.width, row.height, row.bytes = data, mime, w, h, len(data)
    applicant.photo_url = served_url(applicant)
    return row


def save_data_url(applicant, data_url):
    """Store a photo supplied as a ``data:image/...;base64,...`` URL (how the
    admissions form submits it)."""
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
    return save_bytes(applicant, raw)


def delete(applicant):
    from models import db, ApplicantPhoto
    ApplicantPhoto.query.filter_by(applicant_id=applicant.id).delete()
    applicant.photo_url = None


def has_photo(applicant):
    from models import ApplicantPhoto
    return ApplicantPhoto.query.filter_by(applicant_id=applicant.id).first() is not None


def served_url(applicant):
    from flask import url_for
    try:
        return url_for('admissions.applicant_photo', applicant_id=applicant.id)
    except Exception:
        return ''


def load(applicant_id):
    """(bytes, mime) for an applicant's photo, or (None, None)."""
    from models import ApplicantPhoto
    row = ApplicantPhoto.query.filter_by(applicant_id=applicant_id).first()
    if row is None or not row.data:
        return None, None
    return bytes(row.data), (row.mime or 'image/jpeg')
