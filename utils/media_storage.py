"""Pluggable storage backend for Website-Builder images.

Three backends, chosen by ``WEBSITE_MEDIA_BACKEND``:

* ``db``  (default) — bytes live in the school's own tenant DB (``SiteMedia.data``).
  Zero-config and perfectly isolated; ideal for the handful of images a school
  site needs.
* ``local`` — bytes on a filesystem volume (``WEBSITE_MEDIA_LOCAL_DIR``),
  namespaced per tenant. Use with a persistent volume (+ optional CDN).
* ``s3`` — S3-compatible object storage (AWS S3 / Cloudflare R2 / MinIO) via
  boto3, namespaced per tenant. The recommended pattern at scale.

The DB stores only metadata plus a ``storage`` name and ``storage_key``. When
``WEBSITE_MEDIA_PUBLIC_BASE`` is set, images are served straight from that
CDN/bucket base (no app hop); otherwise the app's cached, publish-gated route
streams them from whichever backend holds the bytes.
"""
import os
import uuid


def backend():
    from flask import current_app
    return (current_app.config.get('WEBSITE_MEDIA_BACKEND') or 'db').lower()


def _tenant_prefix():
    """A per-school key prefix so one bucket/dir is namespaced by tenant."""
    try:
        from utils.tenant_runtime import current_tenant
        t = current_tenant()
        if t is not None:
            return t.subdomain
    except Exception:
        pass
    return 'default'


def _ext_for(mime):
    return {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp',
            'image/gif': 'gif'}.get(mime, 'bin')


def _local_dir():
    from flask import current_app
    return current_app.config.get('WEBSITE_MEDIA_LOCAL_DIR')


def _s3_client():
    from flask import current_app
    cfg = current_app.config
    try:
        import boto3
    except ImportError:
        raise RuntimeError('WEBSITE_MEDIA_BACKEND=s3 needs boto3 installed.')
    kwargs = {'region_name': cfg.get('WEBSITE_MEDIA_S3_REGION') or 'auto'}
    if cfg.get('WEBSITE_MEDIA_S3_ENDPOINT'):
        kwargs['endpoint_url'] = cfg['WEBSITE_MEDIA_S3_ENDPOINT']
    if cfg.get('WEBSITE_MEDIA_S3_KEY'):
        kwargs['aws_access_key_id'] = cfg['WEBSITE_MEDIA_S3_KEY']
        kwargs['aws_secret_access_key'] = cfg['WEBSITE_MEDIA_S3_SECRET']
    return boto3.client('s3', **kwargs)


def store(raw, mime):
    """Persist ``raw`` bytes to the configured backend. Returns
    ``(storage, storage_key)``; for the DB backend the key is None and the
    caller keeps the bytes on the row."""
    be = backend()
    if be == 'db':
        return 'db', None
    key = 'website/%s/%s.%s' % (_tenant_prefix(), uuid.uuid4().hex, _ext_for(mime))
    if be == 'local':
        path = os.path.join(_local_dir(), key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as fh:
            fh.write(raw)
        return 'local', key
    if be == 's3':
        from flask import current_app
        _s3_client().put_object(Bucket=current_app.config['WEBSITE_MEDIA_S3_BUCKET'],
                                Key=key, Body=raw, ContentType=mime,
                                CacheControl='public, max-age=31536000, immutable')
        return 's3', key
    raise RuntimeError('Unknown WEBSITE_MEDIA_BACKEND: %r' % be)


def load(media):
    """Return the image bytes for ``media`` from wherever they live."""
    if media.storage == 'db' or media.data is not None:
        return media.data
    if media.storage == 'local':
        with open(os.path.join(_local_dir(), media.storage_key), 'rb') as fh:
            return fh.read()
    if media.storage == 's3':
        from flask import current_app
        obj = _s3_client().get_object(Bucket=current_app.config['WEBSITE_MEDIA_S3_BUCKET'],
                                      Key=media.storage_key)
        return obj['Body'].read()
    return media.data


def public_url(media):
    """A direct, cacheable URL for ``media`` when a public base is configured
    (so pages reference the CDN/bucket instead of hopping through the app).
    None means "serve via the app route" (the default, which keeps the
    draft/publish gate)."""
    from flask import current_app
    base = current_app.config.get('WEBSITE_MEDIA_PUBLIC_BASE')
    if base and getattr(media, 'storage', 'db') != 'db' and media.storage_key:
        return '%s/%s' % (base, media.storage_key)
    return None


def delete(media):
    """Best-effort removal of the stored bytes (the row is deleted separately)."""
    try:
        if media.storage == 'local' and media.storage_key:
            path = os.path.join(_local_dir(), media.storage_key)
            if os.path.exists(path):
                os.remove(path)
        elif media.storage == 's3' and media.storage_key:
            from flask import current_app
            _s3_client().delete_object(Bucket=current_app.config['WEBSITE_MEDIA_S3_BUCKET'],
                                       Key=media.storage_key)
    except Exception:
        pass
