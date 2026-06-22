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
