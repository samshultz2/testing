"""Periodic cleanup of stale on-disk media.

The only media that lands as *loose files* on disk is communication attachments
(``uploads/<tenant>/comm/``). Student passports live in the DB and are replaced
in place; the school logo is a single fixed path that's overwritten; website
images live in the DB (``SiteMedia``) and are managed through the media library —
none of those accumulate orphans. So this sweep targets orphaned comm files:
files with no ``CommAttachment`` row.

Conservative by design: a file is only removed when it has **no DB reference**
*and* is older than a grace window, so a file that was just saved but whose row
hasn't committed yet (an in-flight upload) is never deleted. Runs per-tenant from
the daily jobs (``app._tick_one``), and on demand via
``scripts/cleanup_media.py``.
"""
from __future__ import annotations

import os
import time

GRACE_SECONDS = 24 * 3600   # never touch a file younger than this


def sweep_comm_orphans(grace_seconds: int = GRACE_SECONDS):
    """Delete files in the current tenant's comm-attachment folder that have no
    ``CommAttachment`` row and are older than the grace window.

    Returns ``(deleted_count, freed_bytes)``. Best-effort — never raises.
    """
    from models import db, CommAttachment
    from utils import comm_attachments
    try:
        folder = comm_attachments._folder()
    except Exception:
        return (0, 0)
    try:
        referenced = {a.stored_name for a in CommAttachment.query.all()}
    except Exception:
        db.session.rollback()
        return (0, 0)
    try:
        names = os.listdir(folder)
    except OSError:
        return (0, 0)
    now = time.time()
    deleted = 0
    freed = 0
    for name in names:
        if name in referenced:
            continue
        path = os.path.join(folder, name)
        try:
            if not os.path.isfile(path):
                continue
            if now - os.path.getmtime(path) < grace_seconds:
                continue                       # too new — maybe an in-flight upload
            size = os.path.getsize(path)
            os.remove(path)
            deleted += 1
            freed += size
        except OSError:
            continue
    return (deleted, freed)


def sweep_current_tenant(grace_seconds: int = GRACE_SECONDS):
    """Run every disk-media sweep against the currently-bound tenant DB + upload
    folder. Returns a summary dict."""
    deleted, freed = sweep_comm_orphans(grace_seconds)
    return {'comm_deleted': deleted, 'comm_freed': freed}
