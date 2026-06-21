"""Online payments (Paystack): disabled-by-default, and verified callback records a fee."""
import re
from models import db, Student, AcademicSession, Term, FeePayment, Branch


def _student_and_term(app):
    with app.app_context():
        s = Student.query.filter_by(student_id='PAY1').first()
        if not s:
            s = Student(student_id='PAY1', first_name='Pay', surname='Kid', gender='Male',
                        is_active=True, branch_id=Branch.get_default().id)
            s.set_portal_password('pass123'); db.session.add(s); db.session.flush()
            sess = AcademicSession(name='PAY-Sess'); db.session.add(sess); db.session.flush()
            t = Term(session_id=sess.id, term_number=1, name='PAY-Term'); db.session.add(t)
            db.session.commit()
        t = Term.query.filter_by(name='PAY-Term').first()
        return s.id, t.id


def _login(app):
    sid, tid = _student_and_term(app)
    c = app.test_client()
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                    c.get('/parent/login').get_data(as_text=True)).group(1)
    c.post('/parent/login', data={'student_id': 'PAY1', 'password': 'pass123', '_csrf_token': tok})
    # The CSRF token rotates on login (fixation fix) — return the current one.
    with c.session_transaction() as sess:
        tok = sess.get('_csrf_token', tok)
    return c, sid, tid, tok


def test_payment_disabled_without_keys(app):
    from utils import payments
    assert payments.is_configured() is False     # no keys in test config
    c, sid, tid, tok = _login(app)
    r = c.post('/parent/pay', data={'amount': '5000', 'term_id': tid, '_csrf_token': tok},
               follow_redirects=False)
    assert r.status_code in (302, 303)            # bounced (not available)
    with app.app_context():
        assert FeePayment.query.filter_by(student_id=sid).count() == 0


def test_verified_callback_records_payment_once(app, monkeypatch):
    from utils import payments
    c, sid, tid, tok = _login(app)
    ref = 'PSK-test-123'
    monkeypatch.setattr(payments, 'verify', lambda r: {
        'ok': True, 'success': True, 'amount_naira': 5000.0, 'reference': r})
    with c.session_transaction() as s:
        s['pay_ref'] = {'ref': ref, 'student_id': sid, 'term_id': tid, 'amount': 5000.0}
    c.get(f'/parent/pay/callback?reference={ref}', follow_redirects=False)
    with app.app_context():
        pays = FeePayment.query.filter_by(reference=ref).all()
        assert len(pays) == 1
        assert pays[0].amount == 5000.0 and pays[0].method == 'Online'
    # idempotent: a replayed callback does not double-record
    with c.session_transaction() as s:
        s['pay_ref'] = {'ref': ref, 'student_id': sid, 'term_id': tid, 'amount': 5000.0}
    c.get(f'/parent/pay/callback?reference={ref}', follow_redirects=False)
    with app.app_context():
        assert FeePayment.query.filter_by(reference=ref).count() == 1


def test_webhook_records_with_valid_signature(app, monkeypatch):
    import hmac, hashlib, json
    from config import Config
    monkeypatch.setattr(Config, 'PAYSTACK_SECRET_KEY', 'sk_test_secret', raising=False)
    sid, tid = _student_and_term(app)
    ref = 'PSK-webhook-1'
    payload = {'event': 'charge.success',
               'data': {'status': 'success', 'reference': ref, 'amount': 750000,
                        'metadata': {'student_id': sid, 'term_id': tid}}}
    body = json.dumps(payload).encode()
    sig = hmac.new(b'sk_test_secret', body, hashlib.sha512).hexdigest()
    c = app.test_client()
    # bad signature rejected
    bad = c.post('/parent/pay/webhook', data=body, headers={'x-paystack-signature': 'deadbeef',
                                                            'Content-Type': 'application/json'})
    assert bad.status_code == 400
    # good signature records once
    ok = c.post('/parent/pay/webhook', data=body, headers={'x-paystack-signature': sig,
                                                           'Content-Type': 'application/json'})
    assert ok.status_code == 200
    with app.app_context():
        from models import FeePayment
        rows = FeePayment.query.filter_by(reference=ref).all()
        assert len(rows) == 1 and rows[0].amount == 7500.0 and rows[0].method == 'Online'
    # replay is idempotent
    c.post('/parent/pay/webhook', data=body, headers={'x-paystack-signature': sig,
                                                      'Content-Type': 'application/json'})
    with app.app_context():
        from models import FeePayment
        assert FeePayment.query.filter_by(reference=ref).count() == 1
