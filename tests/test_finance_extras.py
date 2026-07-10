"""Finance Phase 5 extras: global search, saved-view widget, per-item sale
categorisation, and the parent fee-reminder draft handoff."""
import re

from models import db, Branch


def _admin(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['role'] = 'super_admin'
    return c


def _csrf(client, url='/finance/installments'):
    page = client.get(url).get_data(as_text=True)
    m = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', page)
    return m.group(1) if m else 'a' * 64


# --- global search ----------------------------------------------------------
def test_search_page_renders_and_prompts(app):
    c = _admin(app)
    r = c.get('/finance/search')
    assert r.status_code == 200
    assert 'Search finance' in r.get_data(as_text=True)


def test_search_finds_a_student(app):
    from models import Student
    with app.app_context():
        s = Student(student_id='FINSRCH01', first_name='Zzquux', surname='Searchme',
                    gender='Male', is_active=True)
        db.session.add(s)
        db.session.commit()
    c = _admin(app)
    body = c.get('/finance/search?q=Zzquux').get_data(as_text=True)
    assert 'Searchme' in body and 'FINSRCH01' in body


def test_search_short_query_asks_for_more(app):
    c = _admin(app)
    body = c.get('/finance/search?q=a').get_data(as_text=True)
    assert 'at least two characters' in body


# --- saved-view widget is present on the filter bars ------------------------
def test_saved_views_widget_on_overview_and_accounting(app):
    c = _admin(app)
    for url in ('/finance/overview', '/finance/accounting'):
        body = c.get(url).get_data(as_text=True)
        assert 'data-views-key' in body and 'Saved views' in body


# --- keyboard-shortcut scaffolding is shipped -------------------------------
def test_finance_header_ships_shortcut_map(app):
    c = _admin(app)
    body = c.get('/finance/overview').get_data(as_text=True)
    assert 'fin-nav-urls' in body and 'finKbdHelp' in body


# --- per-item sale categorisation ------------------------------------------
def test_sale_category_buckets():
    from utils.finance_ledger import sale_category
    assert sale_category(['Uniform']) == 'Uniform'
    assert sale_category(['Textbook', 'Workbook']) == 'Bookshop'
    assert sale_category(['Uniform', 'Textbook']) == 'Mixed sales'
    assert sale_category([]) == 'Sales'
    assert sale_category([None]) == 'Sales'


def test_sale_posts_bucketed_category_to_ledger(app):
    from models import Product, Sale, SaleItem, FinanceTransaction
    with app.app_context():
        bid = Branch.get_default().id
        p = Product(branch_id=bid, name='School Beret', category='Uniform',
                    unit_price=1500, stock_qty=10)
        db.session.add(p)
        db.session.flush()
        sale = Sale(branch_id=bid, payment_method='Cash', total=1500, amount_paid=1500,
                    sold_by='Tester')
        from utils.finance_ledger import sale_category
        sale._ledger_category = sale_category([p.category])
        db.session.add(sale)
        db.session.flush()
        sale.receipt_no = f'SL{sale.id:05d}'
        db.session.add(SaleItem(sale_id=sale.id, product_id=p.id, description=p.name,
                                quantity=1, unit_price=1500, line_total=1500))
        db.session.commit()
        txn = (FinanceTransaction.query
               .filter_by(origin_type='sale', origin_id=sale.id).first())
        assert txn is not None and txn.category == 'Uniform'


# --- parent fee-reminder draft handoff --------------------------------------
def test_draft_reminders_requires_term(app):
    c = _admin(app)
    tok = _csrf(c)
    r = c.post('/finance/reminders/draft', data={'_csrf_token': tok, 'term_id': 0},
               follow_redirects=False)
    # no valid term -> stays put with an error (redirect back), never 500
    assert r.status_code in (200, 302, 303)


def test_draft_reminders_with_no_defaulters(app):
    from utils.helpers import get_active_term
    c = _admin(app)
    with app.app_context():
        t = get_active_term()
        tid = t.id if t else None
    if not tid:
        return
    tok = _csrf(c)
    for channel in ('SMS', 'Email'):
        r = c.post('/finance/reminders/draft',
                   data={'_csrf_token': tok, 'term_id': tid, 'channel': channel},
                   follow_redirects=False)
        assert r.status_code in (200, 302, 303)


def test_installments_offers_channel_choice(app):
    from models import Term
    c = _admin(app)
    with app.app_context():
        t = Term.query.first()
        tid = t.id if t else None
    if not tid:
        return
    body = c.get(f'/finance/installments?term_id={tid}').get_data(as_text=True)
    assert 'name="channel"' in body and 'Message parents' in body


# --- parent email storage + email dispatch ----------------------------------
def test_parent_contact_and_recipient_store_email(app):
    from models import Student, ParentContact, Message, MessageRecipient
    with app.app_context():
        # inactive so it stays out of shared-DB audience/ordering in other tests
        s = Student(student_id='EMAILP01', first_name='Em', surname='Ail',
                    gender='Male', is_active=False)
        db.session.add(s)
        db.session.flush()
        db.session.add(ParentContact(student_id=s.id, phone_number='08011112222',
                                     email='par@example.com', name='Par', is_primary=True))
        m = Message(title='Fees', body='hi', channel='Email', status='Draft',
                    recipient_count=1)
        db.session.add(m)
        db.session.flush()
        db.session.add(MessageRecipient(message_id=m.id, parent_name='Par',
                                        email='par@example.com', body='Dear Par'))
        db.session.commit()
        assert ParentContact.query.filter_by(student_id=s.id).first().email == 'par@example.com'
        assert MessageRecipient.query.filter_by(message_id=m.id).first().email == 'par@example.com'


def test_dispatch_campaign_email_uses_mailer(app, monkeypatch):
    from models import Message, MessageRecipient
    from utils import comms, mailer
    sent = []
    monkeypatch.setattr(mailer, 'send_email',
                        lambda to, subject, body, html=None: (sent.append((to, subject)) or True))
    with app.app_context():
        m = Message(title='Fee reminder', body='hi', channel='Email',
                    status='Sending', recipient_count=1)
        db.session.add(m)
        db.session.flush()
        db.session.add(MessageRecipient(message_id=m.id, parent_name='P',
                                        email='a@b.com', body='Dear P', status='Pending'))
        db.session.commit()
        s, f = comms.dispatch_campaign_email(m)
        assert (s, f) == (1, 0)
        assert sent and sent[0][0] == 'a@b.com'
        assert MessageRecipient.query.filter_by(message_id=m.id).first().status == 'Sent'


def test_dispatch_email_fails_without_address(app, monkeypatch):
    from models import Message, MessageRecipient
    from utils import comms, mailer
    monkeypatch.setattr(mailer, 'send_email', lambda *a, **k: True)
    with app.app_context():
        m = Message(title='Fee reminder', body='hi', channel='Email',
                    status='Sending', recipient_count=1)
        db.session.add(m)
        db.session.flush()
        db.session.add(MessageRecipient(message_id=m.id, parent_name='P',
                                        email=None, body='x', status='Pending'))
        db.session.commit()
        s, f = comms.dispatch_campaign_email(m)
        assert (s, f) == (0, 1)


def test_email_campaign_send_refused_without_smtp(app):
    """An Email campaign renders and its send is refused (not crashed) when SMTP
    is unconfigured — the default in tests."""
    from models import Message
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['logged_in'] = True
        sess['role'] = 'super_admin'
        sess['_csrf_token'] = 'a' * 64
    with app.app_context():
        m = Message(title='Fees', body='hi', channel='Email', status='Draft',
                    recipient_count=0)
        db.session.add(m)
        db.session.commit()
        mid = m.id
    assert c.get(f'/communication/messages/{mid}').status_code == 200
    r = c.post(f'/communication/messages/{mid}/send-gateway',
               data={'_csrf_token': 'a' * 64}, follow_redirects=False)
    assert r.status_code in (302, 303)
