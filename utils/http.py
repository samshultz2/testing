"""Minimal, dependency-free JSON HTTP for outbound API calls (Paystack).

Uses only the Python standard library, so it can't be broken by a mismatched
``requests`` / ``urllib3`` in the deployment environment (which can silently
ignore timeouts and hang a request forever). It exposes just what the billing
code needs — a JSON POST/GET with a reliable socket timeout — behind a tiny
``requests``-like response object (``.status_code`` / ``.json()`` / ``.ok`` /
``.content``).

Network/timeout failures raise (like ``requests`` does) so callers' existing
try/except handles them; HTTP error statuses (e.g. 401 for a bad key) return a
normal result so the JSON error body can be read.
"""
from __future__ import annotations

import json as _json
import urllib.request
import urllib.error

# urllib's default User-Agent is "Python-urllib/x.y", which Cloudflare-fronted
# APIs (Paystack) block with a 403. Send an explicit, well-behaved UA + Accept so
# the request is allowed through. Callers can still override either header.
_DEFAULT_HEADERS = {
    'User-Agent': 'EduSyncra/1.0 (+https://edusyncra.site)',
    'Accept': 'application/json',
}


class HttpResult:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body or ''

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    @property
    def content(self):
        return self._body

    def json(self):
        try:
            return _json.loads(self._body or '{}')
        except ValueError:
            return {}


def _read_timeout(timeout):
    # Accept a requests-style (connect, read) tuple or a single number; urllib's
    # socket timeout applies per operation, so use the larger (read) value.
    if isinstance(timeout, (tuple, list)):
        return max(timeout)
    return timeout


def request_json(method, url, headers=None, json=None, timeout=20):
    """Perform a JSON request and return an HttpResult. Raises on network/timeout
    errors; returns the response (with its body) even on 4xx/5xx."""
    data = _json.dumps(json).encode('utf-8') if json is not None else None
    hdrs = dict(_DEFAULT_HEADERS)
    hdrs.update(headers or {})                        # caller's Authorization/etc. win
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=_read_timeout(timeout)) as resp:
            return HttpResult(resp.status, resp.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as e:
        # Paystack sends a JSON error body with a 4xx (e.g. invalid key) — keep it.
        body = ''
        try:
            body = e.read().decode('utf-8', 'replace')
        except Exception:
            pass
        return HttpResult(e.code, body)


def post_json(url, headers=None, json=None, timeout=20):
    return request_json('POST', url, headers=headers, json=json, timeout=timeout)


def get_json(url, headers=None, timeout=20):
    return request_json('GET', url, headers=headers, timeout=timeout)
