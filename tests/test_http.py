"""utils.http — the dependency-free JSON client used for Paystack calls."""
import io
import json
import urllib.error
from unittest.mock import patch

from utils import http


class _FakeResp:
    def __init__(self, status, body):
        self.status = status
        self._body = body.encode()
    def read(self):
        return self._body
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def test_read_timeout_accepts_tuple_or_number():
    assert http._read_timeout(20) == 20
    assert http._read_timeout((8, 25)) == 25          # uses the read (larger) value


def test_post_json_sends_body_and_parses_response():
    captured = {}
    def fake_urlopen(req, timeout=None):
        captured['url'] = req.full_url
        captured['method'] = req.get_method()
        captured['timeout'] = timeout
        captured['body'] = req.data
        return _FakeResp(200, json.dumps({'status': True, 'data': {'authorization_url': 'x'}}))
    with patch('urllib.request.urlopen', fake_urlopen):
        r = http.post_json('https://api.test/pay', headers={'Authorization': 'Bearer k'},
                           json={'amount': 500000}, timeout=(8, 20))
    assert r.ok and r.status_code == 200
    assert r.json()['data']['authorization_url'] == 'x'
    assert captured['method'] == 'POST' and captured['timeout'] == 20
    assert json.loads(captured['body']) == {'amount': 500000}


def test_http_error_returns_body_not_raises():
    err = urllib.error.HTTPError('u', 401, 'Unauthorized', {},
                                 io.BytesIO(json.dumps({'status': False, 'message': 'Invalid key'}).encode()))
    with patch('urllib.request.urlopen', side_effect=err):
        r = http.post_json('https://api.test/pay', json={})
    assert r.status_code == 401 and not r.ok
    assert r.json()['message'] == 'Invalid key'


def test_network_error_propagates():
    import pytest
    with patch('urllib.request.urlopen', side_effect=urllib.error.URLError('timed out')):
        with pytest.raises(urllib.error.URLError):
            http.get_json('https://api.test/verify/ref')
