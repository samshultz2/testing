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
    r = c.post('/finance/reminders/draft',
               data={'_csrf_token': tok, 'term_id': tid},
               follow_redirects=False)
    assert r.status_code in (200, 302, 303)
