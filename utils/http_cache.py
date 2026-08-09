"""Small HTTP conditional-request helpers (ETag / 304).

For deterministic, data-derived responses (a generated PDF, an Excel export, a
JSON payload) a strong ETag lets an unchanged re-request return a cheap 304
instead of regenerating and re-sending the whole body — a real win on mobile and
poor connections. Not for HTML pages that embed a per-request CSRF token or CSP
nonce: those bodies differ every request, so an ETag would never match and could
serve a stale token.
"""
import hashlib

from flask import request, Response


def strong_etag(*parts):
    """A strong ETag from arbitrary parts (stringified and joined)."""
    raw = '||'.join('' if p is None else str(p) for p in parts)
    return '"' + hashlib.sha1(raw.encode('utf-8')).hexdigest() + '"'


def if_none_match(etag):
    """The 304 Response to return when the client already holds ``etag`` (via
    If-None-Match), else None. Handles a comma-separated header and ignores weak
    'W/' prefixes on the client's tags."""
    header = request.headers.get('If-None-Match') or ''
    tags = {t.strip().lstrip('W/').strip() for t in header.split(',') if t.strip()}
    if etag in tags or etag.lstrip('W/').strip() in tags:
        return stamp(Response(status=304), etag)
    return None


def stamp(resp, etag, *, max_age=0, private=True):
    """Attach the ETag and a revalidate-friendly Cache-Control to a response."""
    resp.headers['ETag'] = etag
    scope = 'private' if private else 'public'
    resp.headers['Cache-Control'] = f'{scope}, max-age={max_age}, must-revalidate'
    return resp
