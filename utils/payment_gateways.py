"""Pluggable payment gateways for school-fee collection.

One small interface, several providers, so a school can collect through whichever
gateway it has an account with. Each provider implements:

    initialize(keys, email, amount_naira, reference, callback_url, metadata)
        -> {'ok': True, 'authorization_url': ..., 'reference': ...} | {'ok': False, 'error': ...}
    verify(keys, reference)
        -> {'ok': True, 'success': bool, 'amount_naira': float, 'reference': ...} | {'ok': False, 'error'}
    verify_webhook(keys, headers, body_bytes)
        -> {'ok': bool (signature valid), 'event': {reference, amount_naira, success, metadata}}

`keys` is a dict {'public','secret','extra'} of the school's stored credentials.
All HTTP goes through utils.http (stdlib — no hang, WAF-friendly User-Agent).

Paystack is the proven path; Flutterwave and Monnify follow each provider's
documented API and should be validated with the provider's test keys before
going live. Remita is intentionally left out for now (RRR flow differs enough to
warrant its own pass).
"""
from __future__ import annotations

import hashlib
import hmac

PROVIDERS = ('paystack', 'flutterwave', 'monnify')
PROVIDER_LABELS = {'paystack': 'Paystack', 'flutterwave': 'Flutterwave', 'monnify': 'Monnify'}


def _http():
    from utils import http
    return http


# ---- Paystack --------------------------------------------------------------
_PAYSTACK = 'https://api.paystack.co'


def _paystack_headers(keys):
    return {'Authorization': f'Bearer {keys.get("secret", "")}', 'Content-Type': 'application/json'}


def _paystack_initialize(keys, email, amount_naira, reference, callback_url, metadata):
    r = _http().post_json(f'{_PAYSTACK}/transaction/initialize', headers=_paystack_headers(keys),
                          json={'email': email or 'parent@example.com',
                                'amount': int(round(amount_naira * 100)), 'reference': reference,
                                'callback_url': callback_url, 'metadata': metadata}, timeout=20)
    d = r.json()
    if d.get('status') and (d.get('data') or {}).get('authorization_url'):
        return {'ok': True, 'authorization_url': d['data']['authorization_url'], 'reference': reference}
    return {'ok': False, 'error': d.get('message', 'Could not start payment.')}


def _paystack_verify(keys, reference):
    r = _http().get_json(f'{_PAYSTACK}/transaction/verify/{reference}', headers=_paystack_headers(keys), timeout=20)
    d = r.json()
    if d.get('status'):
        x = d.get('data') or {}
        return {'ok': True, 'success': x.get('status') == 'success',
                'amount_naira': (x.get('amount', 0) or 0) / 100.0, 'reference': x.get('reference', reference)}
    return {'ok': False, 'error': d.get('message', 'Verification failed.')}


def _paystack_webhook(keys, headers, body):
    sig = headers.get('x-paystack-signature', '')
    expected = hmac.new((keys.get('secret') or '').encode(), body, hashlib.sha512).hexdigest()
    if not sig or not hmac.compare_digest(expected, sig):
        return {'ok': False}
    import json
    e = json.loads(body or b'{}')
    d = e.get('data') or {}
    return {'ok': True, 'event': {'reference': d.get('reference'),
                                  'amount_naira': (d.get('amount', 0) or 0) / 100.0,
                                  'success': d.get('status') == 'success',
                                  'metadata': d.get('metadata') or {}}}


# ---- Flutterwave -----------------------------------------------------------
_FLW = 'https://api.flutterwave.com/v3'


def _flw_headers(keys):
    return {'Authorization': f'Bearer {keys.get("secret", "")}', 'Content-Type': 'application/json'}


def _flw_initialize(keys, email, amount_naira, reference, callback_url, metadata):
    r = _http().post_json(f'{_FLW}/payments', headers=_flw_headers(keys),
                          json={'tx_ref': reference, 'amount': round(amount_naira, 2), 'currency': 'NGN',
                                'redirect_url': callback_url, 'customer': {'email': email or 'parent@example.com'},
                                'meta': metadata}, timeout=20)
    d = r.json()
    if d.get('status') == 'success' and (d.get('data') or {}).get('link'):
        return {'ok': True, 'authorization_url': d['data']['link'], 'reference': reference}
    return {'ok': False, 'error': d.get('message', 'Could not start payment.')}


def _flw_verify(keys, reference):
    r = _http().get_json(f'{_FLW}/transactions/verify_by_reference?tx_ref={reference}',
                         headers=_flw_headers(keys), timeout=20)
    d = r.json()
    if d.get('status') == 'success':
        x = d.get('data') or {}
        return {'ok': True, 'success': x.get('status') == 'successful',
                'amount_naira': float(x.get('amount', 0) or 0), 'reference': x.get('tx_ref', reference)}
    return {'ok': False, 'error': d.get('message', 'Verification failed.')}


def _flw_webhook(keys, headers, body):
    # Flutterwave sends the dashboard-configured secret hash in 'verif-hash'.
    verif = headers.get('verif-hash', '')
    if not verif or verif != (keys.get('extra') or keys.get('secret') or ''):
        return {'ok': False}
    import json
    e = json.loads(body or b'{}')
    d = e.get('data') or e
    return {'ok': True, 'event': {'reference': d.get('tx_ref') or d.get('txRef'),
                                  'amount_naira': float(d.get('amount', 0) or 0),
                                  'success': d.get('status') == 'successful',
                                  'metadata': d.get('meta') or {}}}


# ---- Monnify ---------------------------------------------------------------
_MONNIFY = 'https://api.monnify.com'


def _monnify_token(keys):
    import base64
    basic = base64.b64encode(f'{keys.get("public","")}:{keys.get("secret","")}'.encode()).decode()
    r = _http().post_json(f'{_MONNIFY}/api/v1/auth/login',
                          headers={'Authorization': f'Basic {basic}', 'Content-Type': 'application/json'},
                          json={}, timeout=20)
    d = r.json()
    return ((d.get('responseBody') or {}).get('accessToken')) if d.get('requestSuccessful') else None


def _monnify_initialize(keys, email, amount_naira, reference, callback_url, metadata):
    token = _monnify_token(keys)
    if not token:
        return {'ok': False, 'error': 'Could not authenticate with Monnify.'}
    r = _http().post_json(f'{_MONNIFY}/api/v1/merchant/transactions/init-transaction',
                          headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                          json={'amount': round(amount_naira, 2), 'customerName': (metadata or {}).get('name', 'Parent'),
                                'customerEmail': email or 'parent@example.com', 'paymentReference': reference,
                                'paymentDescription': 'School fees', 'currencyCode': 'NGN',
                                'contractCode': keys.get('extra', ''), 'redirectUrl': callback_url}, timeout=20)
    d = r.json()
    body = d.get('responseBody') or {}
    if d.get('requestSuccessful') and body.get('checkoutUrl'):
        return {'ok': True, 'authorization_url': body['checkoutUrl'], 'reference': reference}
    return {'ok': False, 'error': d.get('responseMessage', 'Could not start payment.')}


def _monnify_verify(keys, reference):
    token = _monnify_token(keys)
    if not token:
        return {'ok': False, 'error': 'Could not authenticate with Monnify.'}
    from urllib.parse import quote
    r = _http().get_json(f'{_MONNIFY}/api/v2/merchant/transactions/query?paymentReference={quote(reference)}',
                         headers={'Authorization': f'Bearer {token}'}, timeout=20)
    d = r.json()
    if d.get('requestSuccessful'):
        x = d.get('responseBody') or {}
        return {'ok': True, 'success': x.get('paymentStatus') == 'PAID',
                'amount_naira': float(x.get('amountPaid', 0) or 0), 'reference': x.get('paymentReference', reference)}
    return {'ok': False, 'error': d.get('responseMessage', 'Verification failed.')}


def _monnify_webhook(keys, headers, body):
    sig = headers.get('monnify-signature', '')
    expected = hmac.new((keys.get('secret') or '').encode(), body, hashlib.sha512).hexdigest()
    if not sig or not hmac.compare_digest(expected, sig):
        return {'ok': False}
    import json
    e = json.loads(body or b'{}')
    d = e.get('eventData') or e.get('data') or {}
    return {'ok': True, 'event': {'reference': d.get('paymentReference'),
                                  'amount_naira': float(d.get('amountPaid', 0) or 0),
                                  'success': (d.get('paymentStatus') == 'PAID'),
                                  'metadata': d.get('metaData') or {}}}


_IMPL = {
    'paystack': (_paystack_initialize, _paystack_verify, _paystack_webhook),
    'flutterwave': (_flw_initialize, _flw_verify, _flw_webhook),
    'monnify': (_monnify_initialize, _monnify_verify, _monnify_webhook),
}


# ---- public dispatch -------------------------------------------------------
def initialize(provider, keys, *, email, amount_naira, reference, callback_url, metadata=None):
    impl = _IMPL.get(provider)
    if not impl:
        return {'ok': False, 'error': f'Unknown payment provider: {provider}'}
    try:
        return impl[0](keys, email, amount_naira, reference, callback_url, metadata or {})
    except Exception as exc:
        return {'ok': False, 'error': f'Payment gateway error: {exc}'}


def verify(provider, keys, reference):
    impl = _IMPL.get(provider)
    if not impl:
        return {'ok': False, 'error': f'Unknown payment provider: {provider}'}
    try:
        return impl[1](keys, reference)
    except Exception as exc:
        return {'ok': False, 'error': f'Payment gateway error: {exc}'}


def verify_webhook(provider, keys, headers, body):
    impl = _IMPL.get(provider)
    if not impl:
        return {'ok': False}
    try:
        h = {str(k).lower(): v for k, v in dict(headers).items()}   # case-insensitive
        if isinstance(body, str):
            body = body.encode()
        return impl[2](keys, h, body)
    except Exception:
        return {'ok': False}
