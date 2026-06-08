"""Paystack online-payment integration.

Kept thin and side-effect free so the routes (and tests) can drive it. The whole
feature stays disabled until PAYSTACK_SECRET_KEY is configured.
"""
import secrets
from config import Config

_API = 'https://api.paystack.co'


def is_configured():
    return bool(Config.PAYSTACK_SECRET_KEY)


def public_key():
    return Config.PAYSTACK_PUBLIC_KEY


def new_reference(prefix='PSK'):
    return f'{prefix}-{secrets.token_hex(8)}'


def _headers():
    return {'Authorization': f'Bearer {Config.PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json'}


def initialize(email, amount_naira, reference, callback_url, metadata=None):
    """Start a transaction. Returns {'ok': True, 'authorization_url': ...} or
    {'ok': False, 'error': ...}. Never raises."""
    if not is_configured():
        return {'ok': False, 'error': 'Online payment is not configured.'}
    try:
        import requests
        payload = {
            'email': email or 'parent@example.com',
            'amount': int(round(amount_naira * 100)),   # kobo
            'reference': reference,
            'callback_url': callback_url,
        }
        if metadata:
            payload['metadata'] = metadata
        resp = requests.post(f'{_API}/transaction/initialize', headers=_headers(),
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
        import requests
        resp = requests.get(f'{_API}/transaction/verify/{reference}',
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
