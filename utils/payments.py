"""Paystack online-payment integration for SCHOOL FEES (parents → their school).

Each school collects into its **own** Paystack account. The keys live per-school
in that school's database (SchoolSettings), with the secret key encrypted at rest
(utils.crypto). In a single-school (non-multi-tenant) deployment the keys can also
come from the environment (PAYSTACK_SECRET_KEY) as a fallback.

This is separate from the platform SUBSCRIPTION billing (utils/billing.py +
routes/billing.py), which uses the PLATFORM_PAYSTACK_* keys — schools paying the
platform, not parents paying schools.

Kept thin and side-effect free so the routes (and tests) can drive it. Uses the
dependency-free stdlib HTTP client (utils.http) so a mismatched requests/urllib3
can't hang a payment, and a proper User-Agent gets past Paystack's WAF.
"""
import secrets

from config import Config

_API = 'https://api.paystack.co'

PUBLIC_KEY_SETTING = 'paystack_public_key'
SECRET_KEY_SETTING = 'paystack_secret_key'          # stored encrypted


def _keys():
    """(public, secret) for the CURRENT school. Per-school stored keys win; a
    single-school deployment falls back to the env keys. Multi-tenant never falls
    back to env (that would route a school's money to the platform account)."""
    pub = sec = ''
    try:
        from models import SchoolSettings
        from utils import crypto
        pub = (SchoolSettings.get(PUBLIC_KEY_SETTING, '') or '').strip()
        raw = SchoolSettings.get(SECRET_KEY_SETTING, '') or ''
        sec = (crypto.decrypt(raw) or '').strip() if raw else ''
    except Exception:
        pub, sec = '', ''
    if not sec and not Config.MULTI_TENANT:
        pub = pub or (Config.PAYSTACK_PUBLIC_KEY or '')
        sec = Config.PAYSTACK_SECRET_KEY or ''
    return pub, sec


def is_configured():
    return bool(_keys()[1])


def public_key():
    return _keys()[0]


def secret_key():
    """The current school's Paystack secret (for webhook signature checks)."""
    return _keys()[1]


def save_keys(public_key_value, secret_key_value):
    """Persist this school's Paystack keys (secret encrypted). A blank secret
    means 'leave the stored secret unchanged'; use clear_keys() to remove."""
    from models import SchoolSettings
    from utils import crypto
    SchoolSettings.set(PUBLIC_KEY_SETTING, (public_key_value or '').strip(),
                       'string', 'Paystack public key (online fee payments)')
    sec = (secret_key_value or '').strip()
    if sec:
        SchoolSettings.set(SECRET_KEY_SETTING, crypto.encrypt(sec),
                           'string', 'Paystack secret key (encrypted)')


def clear_keys():
    from models import SchoolSettings
    SchoolSettings.set(PUBLIC_KEY_SETTING, '', 'string')
    SchoolSettings.set(SECRET_KEY_SETTING, '', 'string')


def new_reference(prefix='PSK'):
    return f'{prefix}-{secrets.token_hex(8)}'


def _headers():
    return {'Authorization': f'Bearer {_keys()[1]}',
            'Content-Type': 'application/json'}


def initialize(email, amount_naira, reference, callback_url, metadata=None):
    """Start a transaction. Returns {'ok': True, 'authorization_url': ...} or
    {'ok': False, 'error': ...}. Never raises."""
    if not is_configured():
        return {'ok': False, 'error': 'Online payment is not configured.'}
    try:
        from utils import http
        payload = {
            'email': email or 'parent@example.com',
            'amount': int(round(amount_naira * 100)),   # kobo
            'reference': reference,
            'callback_url': callback_url,
        }
        if metadata:
            payload['metadata'] = metadata
        resp = http.post_json(f'{_API}/transaction/initialize', headers=_headers(),
                              json=payload, timeout=20)
        data = resp.json()
        if data.get('status') and data.get('data', {}).get('authorization_url'):
            return {'ok': True, 'authorization_url': data['data']['authorization_url'],
                    'reference': reference}
        return {'ok': False, 'error': data.get('message', 'Could not start payment.')}
    except Exception as exc:
        return {'ok': False, 'error': f'Payment gateway error: {exc}'}


def verify(reference):
    """Verify a transaction. Returns {'ok': True, 'success': bool,
    'amount_naira': float, 'reference': ...} or {'ok': False, 'error': ...}."""
    if not is_configured():
        return {'ok': False, 'error': 'Online payment is not configured.'}
    try:
        from utils import http
        resp = http.get_json(f'{_API}/transaction/verify/{reference}',
                             headers=_headers(), timeout=20)
        data = resp.json()
        if data.get('status'):
            d = data.get('data', {})
            return {'ok': True, 'success': d.get('status') == 'success',
                    'amount_naira': (d.get('amount', 0) or 0) / 100.0,
                    'reference': d.get('reference', reference)}
        return {'ok': False, 'error': data.get('message', 'Verification failed.')}
    except Exception as exc:
        return {'ok': False, 'error': f'Payment gateway error: {exc}'}
