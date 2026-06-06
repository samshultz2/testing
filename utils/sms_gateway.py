"""
Pluggable SMS gateway.

Schools configure a provider + credentials in Communication → Settings. Until
then everything falls back to manual WhatsApp/SMS deep links. The moment a valid
key is entered, ``send_sms`` starts dispatching server-side — no code change
needed. Supported providers: Termii (Nigeria) and Twilio.

Add a new provider by writing a ``_send_<name>`` function and listing it in
``PROVIDERS`` / ``send_sms``.
"""
from models import SchoolSettings
from utils.comms import normalise_phone

PROVIDERS = {
    'none': 'Manual (WhatsApp / SMS links only)',
    'termii': 'Termii',
    'twilio': 'Twilio',
}

# Setting keys (stored in SchoolSettings).
K_PROVIDER = 'sms_provider'
K_SENDER = 'sms_sender_id'        # Termii sender ID / Twilio "From" number
K_TERMII_KEY = 'termii_api_key'
K_TWILIO_SID = 'twilio_account_sid'
K_TWILIO_TOKEN = 'twilio_auth_token'


def get_config():
    return {
        'provider': SchoolSettings.get(K_PROVIDER, 'none'),
        'sender': SchoolSettings.get(K_SENDER, ''),
        'termii_key': SchoolSettings.get(K_TERMII_KEY, ''),
        'twilio_sid': SchoolSettings.get(K_TWILIO_SID, ''),
        'twilio_token': SchoolSettings.get(K_TWILIO_TOKEN, ''),
    }


def save_config(form):
    """Persist gateway settings from a submitted form dict."""
    SchoolSettings.set(K_PROVIDER, (form.get('provider') or 'none').strip(), 'string', 'SMS provider')
    SchoolSettings.set(K_SENDER, (form.get('sender') or '').strip(), 'string', 'SMS sender ID / from')
    SchoolSettings.set(K_TERMII_KEY, (form.get('termii_key') or '').strip(), 'string', 'Termii API key')
    SchoolSettings.set(K_TWILIO_SID, (form.get('twilio_sid') or '').strip(), 'string', 'Twilio Account SID')
    SchoolSettings.set(K_TWILIO_TOKEN, (form.get('twilio_token') or '').strip(), 'string', 'Twilio Auth Token')


def is_configured(cfg=None):
    """True when the active provider has the credentials it needs to send."""
    cfg = cfg or get_config()
    p = cfg['provider']
    if p == 'termii':
        return bool(cfg['termii_key'] and cfg['sender'])
    if p == 'twilio':
        return bool(cfg['twilio_sid'] and cfg['twilio_token'] and cfg['sender'])
    return False


def provider_label(cfg=None):
    cfg = cfg or get_config()
    return PROVIDERS.get(cfg['provider'], cfg['provider'])


def send_sms(phone, message, cfg=None):
    """
    Send one SMS. Returns (ok: bool, info: str) where info is a provider message
    id on success or an error message on failure.
    """
    cfg = cfg or get_config()
    if not is_configured(cfg):
        return False, 'SMS gateway not configured'
    to = normalise_phone(phone)
    if not to:
        return False, 'Invalid phone number'
    try:
        if cfg['provider'] == 'termii':
            return _send_termii(to, message, cfg)
        if cfg['provider'] == 'twilio':
            return _send_twilio(to, message, cfg)
        return False, 'Unknown provider'
    except Exception as e:  # network/timeouts/etc.
        return False, str(e)


def _send_termii(to, message, cfg):
    import requests
    resp = requests.post('https://api.ng.termii.com/api/sms/send', json={
        'to': to,
        'from': cfg['sender'],
        'sms': message,
        'type': 'plain',
        'channel': 'generic',
        'api_key': cfg['termii_key'],
    }, timeout=20)
    data = {}
    try:
        data = resp.json()
    except Exception:
        pass
    if resp.status_code == 200 and (data.get('message_id') or data.get('code') == 'ok'):
        return True, str(data.get('message_id') or 'sent')
    return False, str(data.get('message') or f'HTTP {resp.status_code}')


def _send_twilio(to, message, cfg):
    import requests
    sid = cfg['twilio_sid']
    resp = requests.post(
        f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json',
        data={'To': '+' + to, 'From': cfg['sender'], 'Body': message},
        auth=(sid, cfg['twilio_token']), timeout=20)
    data = {}
    try:
        data = resp.json()
    except Exception:
        pass
    if resp.status_code in (200, 201) and data.get('sid'):
        return True, data['sid']
    return False, str(data.get('message') or f'HTTP {resp.status_code}')
