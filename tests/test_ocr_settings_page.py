"""AI Vision OCR settings: DB-backed config + masked key in the Settings UI."""
from config import Config
from models import db, SchoolSettings
from tests.conftest import login_token, auth_csrf
from utils import waec_ocr

HDR = {'X-Requested-With': 'fetch'}


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_vision_config_reads_db_settings(app):
    from utils.crypto import encrypt
    with app.app_context():
        SchoolSettings.set('ocr_vision_enabled', True, 'bool')
        SchoolSettings.set('ocr_vision_model', 'claude-sonnet-4-6', 'string')
        SchoolSettings.set('ocr_vision_api_key', encrypt('sk-ant-TESTKEY1234'), 'string')
        db.session.commit()
        cfg = waec_ocr._vision_config()
        assert cfg['enabled'] is True
        assert cfg['model'] == 'claude-sonnet-4-6'
        assert cfg['has_key'] and cfg['key'] == 'sk-ant-TESTKEY1234'      # decrypts back
        assert cfg['key_source'] == 'settings'
        assert 'TESTKEY' not in cfg['key_masked']                        # masked for display
        # anthropic isn't installed here, so it's configured but not yet usable
        assert waec_ocr.vision_available() == (cfg['enabled'] and cfg['has_key'] and cfg['installed'])


def test_ocr_settings_saves_and_masks_key(app):
    c = _admin(app)
    r = c.post('/settings/ocr', headers=HDR, data={
        '_csrf_token': auth_csrf(c), 'enabled': '1',
        'model': 'claude-haiku-4-5', 'api_key': 'sk-ant-SECRETKEY9876'})
    assert r.status_code == 200 and r.get_json()['ok'] is True

    g = c.get('/settings/ocr', headers=HDR)
    data = g.get_json()
    assert data['page'] == 'ocr'
    assert data['enabled'] is True and data['has_key'] is True
    assert data['key_source'] == 'settings'
    assert data['model'] == 'claude-haiku-4-5'
    # The full key is never sent back to the browser; only a masked form.
    assert 'sk-ant-SECRETKEY9876' not in g.get_data(as_text=True)
    assert '9876' in data['key_masked']


def test_ocr_settings_clear_key(app):
    c = _admin(app)
    c.post('/settings/ocr', headers=HDR, data={
        '_csrf_token': auth_csrf(c), 'enabled': '1',
        'model': 'claude-haiku-4-5', 'api_key': 'sk-ant-KEYTOCLEAR1'})
    c.post('/settings/ocr', headers=HDR, data={
        '_csrf_token': auth_csrf(c), 'enabled': '0',
        'model': 'claude-haiku-4-5', 'clear_key': '1'})
    g = c.get('/settings/ocr', headers=HDR).get_json()
    assert g['has_key'] is False and g['enabled'] is False


def _fake_anthropic(behaviour):
    """A stand-in for the anthropic SDK: models.retrieve succeeds or raises."""
    import types
    m = types.ModuleType('anthropic')

    class APIStatusError(Exception):
        status_code = 500

    class AuthenticationError(APIStatusError):
        status_code = 401

    class PermissionDeniedError(APIStatusError):
        status_code = 403

    class NotFoundError(APIStatusError):
        status_code = 404

    class APIConnectionError(Exception):
        pass

    class _Models:
        def retrieve(self, model):
            if behaviour == 'ok':
                return {'id': model}
            raise {'auth': AuthenticationError, 'missing': NotFoundError}[behaviour]()

    class Anthropic:
        def __init__(self, **kw):
            self.models = _Models()

    for k, v in dict(APIStatusError=APIStatusError, AuthenticationError=AuthenticationError,
                     PermissionDeniedError=PermissionDeniedError, NotFoundError=NotFoundError,
                     APIConnectionError=APIConnectionError, Anthropic=Anthropic).items():
        setattr(m, k, v)
    return m


def test_ocr_key_check(app, monkeypatch):
    import sys
    client = _admin(app)
    tok = auth_csrf(client)
    hdr = {'X-Requested-With': 'fetch'}
    monkeypatch.setitem(sys.modules, 'anthropic', _fake_anthropic('ok'))
    r = client.post('/settings/ocr/test', headers=hdr,
                    data={'_csrf_token': tok, 'api_key': 'sk-ant-x', 'model': 'claude-haiku-5-5'}).get_json()
    assert r['ok'] and 'claude-haiku-5-5' in r['message']
    monkeypatch.setitem(sys.modules, 'anthropic', _fake_anthropic('auth'))
    r = client.post('/settings/ocr/test', headers=hdr,
                    data={'_csrf_token': tok, 'api_key': 'sk-ant-bad', 'model': 'claude-haiku-5-5'}).get_json()
    assert not r['ok'] and 'rejected' in r['error']
    monkeypatch.setitem(sys.modules, 'anthropic', _fake_anthropic('missing'))
    r = client.post('/settings/ocr/test', headers=hdr,
                    data={'_csrf_token': tok, 'api_key': 'sk-ant-x', 'model': 'claude-nope'}).get_json()
    assert not r['ok'] and 'claude-nope' in r['error']


def test_ocr_page_lists_models_with_costs(app):
    client = _admin(app)
    d = client.get('/settings/ocr', headers={'X-Requested-With': 'fetch'}).get_json()
    ids = [m['id'] for m in d['model_info']]
    assert 'claude-haiku-5-5' in ids and 'claude-haiku-4-5' in ids
    assert all(m['per_100'] > 0 for m in d['model_info'])
    assert 'test_url' in d and 'last_error' in d
