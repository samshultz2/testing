"""Stale-media cleanup: orphaned comm-attachment files are swept, referenced and
too-new files are kept."""
import os
import time

from models import db, CommAttachment
from utils import comm_attachments
from utils.media_cleanup import sweep_comm_orphans


def _write(folder, name, age_seconds=0):
    path = os.path.join(folder, name)
    with open(path, 'wb') as fh:
        fh.write(b'x' * 32)
    if age_seconds:
        old = time.time() - age_seconds
        os.utime(path, (old, old))
    return path


def test_sweep_removes_only_aged_orphans(app, tmp_path, monkeypatch):
    # Isolate the sweep to a temp folder (never the real uploads/comm).
    folder = str(tmp_path)
    monkeypatch.setattr(comm_attachments, '_folder', lambda: folder)
    with app.app_context():
        # 1) referenced by a CommAttachment row — kept even though aged.
        kept = _write(folder, 'keep_referenced.pdf', age_seconds=48 * 3600)
        db.session.add(CommAttachment(stored_name='keep_referenced.pdf',
                                      original_name='keep.pdf', size=32))
        db.session.commit()
        # 2) orphan, older than the grace window — deleted.
        orphan_old = _write(folder, 'orphan_old.pdf', age_seconds=48 * 3600)
        # 3) orphan, brand new (maybe an in-flight upload) — kept.
        orphan_new = _write(folder, 'orphan_new.pdf', age_seconds=0)

        deleted, freed = sweep_comm_orphans()

        assert deleted == 1 and freed == 32
        assert os.path.exists(kept)
        assert not os.path.exists(orphan_old)
        assert os.path.exists(orphan_new)

        # --now (grace 0) also clears the brand-new orphan, but never the referenced one.
        deleted2, _ = sweep_comm_orphans(grace_seconds=0)
        assert deleted2 == 1
        assert os.path.exists(kept)
        assert not os.path.exists(orphan_new)
