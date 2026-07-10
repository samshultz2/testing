"""Communication attachments — persist an uploaded file to the tenant's upload
folder and record its metadata as a CommAttachment.

Files live on disk (never in the DB); the row keeps the on-disk name, the original
name shown to users, size and content type. Storage is namespaced per school via
``tenant_upload_folder`` so tenants can't read each other's files. Flask's
``MAX_CONTENT_LENGTH`` (16 MB) already caps upload size globally.
"""
from __future__ import annotations

import os
import uuid

from werkzeug.utils import secure_filename

# Document/image types a school actually shares. Deliberately excludes anything
# executable/script-like.
ALLOWED_EXTS = {
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt', 'ppt', 'pptx',
    'png', 'jpg', 'jpeg', 'gif', 'webp', 'zip',
}
_SUBDIR = 'comm'


def _folder():
    from utils.tenant_runtime import tenant_upload_folder
    base = tenant_upload_folder()
    path = os.path.join(base, _SUBDIR)
    os.makedirs(path, exist_ok=True)
    return path


def ext_of(filename):
    return (os.path.splitext(filename or '')[1].lstrip('.') or '').lower()


def save(file_storage, created_by=None):
    """Validate + persist an uploaded file. Returns the CommAttachment, or raises
    ValueError with a user-facing message."""
    from models import db, CommAttachment
    if not file_storage or not file_storage.filename:
        raise ValueError('No file was uploaded.')
    original = secure_filename(file_storage.filename) or 'file'
    ext = ext_of(original)
    if ext not in ALLOWED_EXTS:
        raise ValueError('That file type is not allowed. Use a document, image, CSV or ZIP.')
    stored = f'{uuid.uuid4().hex}.{ext}'
    path = os.path.join(_folder(), stored)
    file_storage.save(path)
    size = os.path.getsize(path)
    att = CommAttachment(stored_name=stored, original_name=original,
                         content_type=(file_storage.mimetype or None),
                         size=size, created_by=created_by)
    db.session.add(att)
    db.session.commit()
    return att


def fs_path(att):
    """Absolute path of an attachment on disk (None if missing)."""
    if att is None:
        return None
    path = os.path.join(_folder(), att.stored_name)
    return path if os.path.exists(path) else None


def delete(att):
    """Remove the file + row. Best-effort on the file."""
    from models import db
    if att is None:
        return
    try:
        p = os.path.join(_folder(), att.stored_name)
        if os.path.exists(p):
            os.remove(p)
    except OSError:
        pass
    db.session.delete(att)
    db.session.commit()


def as_dict(att, *, download_url=None):
    if att is None:
        return None
    return {'id': att.id, 'name': att.original_name, 'size': att.human_size,
            'content_type': att.content_type or '', 'url': download_url}
