"""Multi-gateway payment abstraction: initialize / verify / webhook for
Paystack, Flutterwave and Monnify (HTTP mocked)."""
import hashlib
import hmac
import json
from unittest.mock import patch

from utils import payment_gateways as gw


class Resp:
    def __init__(self, d): self._d = d
    def json(self): return self._d


def test_paystack_flow():
    keys = {'public': 'pk', 'secret': 'sk_x', 'extra': ''}
    with patch('utils.http.post_json', return_value=Resp({'status': True, 'data': {'authorization_url': 'https://ps/checkout'}})):
        r = gw.initialize('paystack', keys, email='a@b.c', amount_naira=5000, reference='r1', callback_url='cb')
    assert r['ok'] and r['authorization_url'].endswith('/checkout')
    with patch('utils.http.get_json', return_value=Resp({'status': True, 'data': {'status': 'success', 'amount': 500000, 'reference': 'r1'}})):
        v = gw.verify('paystack', keys, 'r1')
    assert v['ok'] and v['success'] and v['amount_naira'] == 5000
    body = json.dumps({'event': 'charge.success', 'data': {'status': 'success', 'reference': 'r1', 'amount': 500000, 'metadata': {'x': 1}}}).encode()
    sig = hmac.new(b'sk_x', body, hashlib.sha512).hexdigest()
    w = gw.verify_webhook('paystack', keys, {'X-Paystack-Signature': sig}, body)   # mixed case ok
    assert w['ok'] and w['event']['success'] and w['event']['amount_naira'] == 5000
    assert gw.verify_webhook('paystack', keys, {'x-paystack-signature': 'bad'}, body)['ok'] is False


def test_flutterwave_flow():
    keys = {'public': 'FLWPUBK', 'secret': 'FLWSECK', 'extra': 'hash123'}
    with patch('utils.http.post_json', return_value=Resp({'status': 'success', 'data': {'link': 'https://flw/pay'}})):
        r = gw.initialize('flutterwave', keys, email='a@b.c', amount_naira=5000, reference='r2', callback_url='cb')
    assert r['ok'] and r['authorization_url'] == 'https://flw/pay'
    with patch('utils.http.get_json', return_value=Resp({'status': 'success', 'data': {'status': 'successful', 'amount': 5000, 'tx_ref': 'r2'}})):
        v = gw.verify('flutterwave', keys, 'r2')
    assert v['ok'] and v['success'] and v['amount_naira'] == 5000
    body = json.dumps({'data': {'tx_ref': 'r2', 'amount': 5000, 'status': 'successful', 'meta': {'x': 1}}}).encode()
    assert gw.verify_webhook('flutterwave', keys, {'verif-hash': 'hash123'}, body)['ok'] is True
    assert gw.verify_webhook('flutterwave', keys, {'verif-hash': 'wrong'}, body)['ok'] is False


def test_monnify_flow():
    keys = {'public': 'apikey', 'secret': 'seckey', 'extra': 'CONTRACT'}

    def fake_post(url, headers=None, json=None, timeout=None):
        if 'auth/login' in url:
            return Resp({'requestSuccessful': True, 'responseBody': {'accessToken': 'tok'}})
        if 'init-transaction' in url:
            return Resp({'requestSuccessful': True, 'responseBody': {'checkoutUrl': 'https://monnify/pay'}})
        return Resp({})
    with patch('utils.http.post_json', side_effect=fake_post):
        r = gw.initialize('monnify', keys, email='a@b.c', amount_naira=5000, reference='r3', callback_url='cb')
    assert r['ok'] and r['authorization_url'] == 'https://monnify/pay'

    with patch('utils.http.post_json', return_value=Resp({'requestSuccessful': True, 'responseBody': {'accessToken': 'tok'}})), \
         patch('utils.http.get_json', return_value=Resp({'requestSuccessful': True, 'responseBody': {'paymentStatus': 'PAID', 'amountPaid': 5000, 'paymentReference': 'r3'}})):
        v = gw.verify('monnify', keys, 'r3')
    assert v['ok'] and v['success'] and v['amount_naira'] == 5000

    body = json.dumps({'eventData': {'paymentReference': 'r3', 'amountPaid': 5000, 'paymentStatus': 'PAID', 'metaData': {'x': 1}}}).encode()
    sig = hmac.new(b'seckey', body, hashlib.sha512).hexdigest()
    assert gw.verify_webhook('monnify', keys, {'monnify-signature': sig}, body)['ok'] is True
    assert gw.verify_webhook('monnify', keys, {'monnify-signature': 'bad'}, body)['ok'] is False


def test_facade_selects_provider(app):
    from utils import payments
    with app.app_context():
        payments.save_keys('flutterwave', 'FLWPUBK-x', 'FLWSECK-x', 'hash-x')
        assert payments.active_provider() == 'flutterwave'
        assert payments.is_configured() is True
        assert payments.public_key() == 'FLWPUBK-x'
        payments.save_keys('paystack', 'pk_x', 'sk_x')      # switch back
        assert payments.active_provider() == 'paystack'
        payments.clear_keys()
