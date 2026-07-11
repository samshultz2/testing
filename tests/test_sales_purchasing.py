"""Sales Phase 6 — suppliers, purchase orders, receiving (GRN) and payments."""
import json
from config import Config
from models import (db, Branch, Product, Supplier, PurchaseOrder, StockMovement,
                    SupplierPayment)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return 'a' * 64


def _supplier(app, name='ZzSup'):
    with app.app_context():
        s = Supplier(branch_id=Branch.get_default().id, company_name=name, is_active=True)
        db.session.add(s); db.session.commit()
        return s.id


def _jpost(c, url, body):
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return c.post(url, data=json.dumps(body), content_type='application/json',
                  headers={'X-Requested-With': 'fetch', 'X-CSRFToken': 'a' * 64})


def test_add_supplier_and_list(app):
    c = _admin(app); tok = _csrf(c)
    r = c.post('/sales/suppliers/add', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': tok, 'company_name': 'ZzAcme Books', 'phone': '0801',
                     'contact_person': 'Ada'})
    assert r.status_code == 200 and r.get_json()['ok']
    j = c.get('/sales/suppliers', headers={'X-Requested-With': 'fetch'}).get_json()
    row = next(s for s in j['suppliers'] if s['company_name'] == 'ZzAcme Books')
    assert row['contact_person'] == 'Ada' and row['outstanding'] == 0


def test_po_lifecycle_receive_updates_stock_and_ledger(app):
    c = _admin(app); _csrf(c)
    sid = _supplier(app, 'ZzSupLife')
    with app.app_context():
        p = Product(branch_id=Branch.get_default().id, name='ZzPOBook', category='Textbooks',
                    unit_price=1000, cost_price=500, stock_qty=4, is_active=True)
        db.session.add(p); db.session.commit()
        pid = p.id

    # Create PO submitted for approval.
    r = _jpost(c, '/sales/purchases/new', {
        'supplier_id': sid, 'submit': 'submit',
        'items': [{'product_id': pid, 'quantity': 10, 'unit_cost': 550}]})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        po = PurchaseOrder.query.filter_by(supplier_id=sid).order_by(PurchaseOrder.id.desc()).first()
        assert po.status == 'Pending Approval' and po.total == 5500
        po_id = po.id
        item_id = po.items.first().id

    # Receiving is blocked until approved.
    r = _jpost(c, f'/sales/purchases/{po_id}/receive', {'items': [{'item_id': item_id, 'receive_qty': 10}]})
    assert r.status_code == 400

    # Approve, then partially receive.
    assert _jpost(c, f'/sales/purchases/{po_id}/approve', {}).get_json()['ok']
    assert _jpost(c, f'/sales/purchases/{po_id}/receive',
                  {'items': [{'item_id': item_id, 'receive_qty': 6}]}).get_json()['ok']
    with app.app_context():
        po = db.session.get(PurchaseOrder, po_id)
        assert po.status == 'Partially Received'
        p = db.session.get(Product, pid)
        assert p.stock_qty == 10          # 4 + 6 received
        assert p.cost_price == 550        # valuation updated to latest cost
        mv = StockMovement.query.filter_by(product_id=pid, reason='Stock In (Purchase/GRN)').first()
        assert mv.quantity == 6 and mv.reference == po.po_number

    # Receive the rest → fully received.
    assert _jpost(c, f'/sales/purchases/{po_id}/receive',
                  {'items': [{'item_id': item_id, 'receive_qty': 4}]}).get_json()['ok']
    with app.app_context():
        po = db.session.get(PurchaseOrder, po_id)
        assert po.status == 'Received'
        assert db.session.get(Product, pid).stock_qty == 14


def test_supplier_outstanding_and_payment(app):
    c = _admin(app); _csrf(c)
    sid = _supplier(app, 'ZzSupPay')
    with app.app_context():
        p = Product(branch_id=Branch.get_default().id, name='ZzPayItem', category='Stationery',
                    unit_price=200, cost_price=100, stock_qty=0, is_active=True)
        db.session.add(p); db.session.commit()
        pid = p.id
    r = _jpost(c, '/sales/purchases/new', {'supplier_id': sid, 'submit': 'submit',
              'items': [{'product_id': pid, 'quantity': 5, 'unit_cost': 100}]})
    po_id = None
    with app.app_context():
        po = PurchaseOrder.query.filter_by(supplier_id=sid).order_by(PurchaseOrder.id.desc()).first()
        po_id = po.id; item_id = po.items.first().id
    _jpost(c, f'/sales/purchases/{po_id}/approve', {})
    _jpost(c, f'/sales/purchases/{po_id}/receive', {'items': [{'item_id': item_id, 'receive_qty': 5}]})
    # Received value = 500 → outstanding 500.
    j = c.get(f'/sales/suppliers/{sid}', headers={'X-Requested-With': 'fetch'}).get_json()
    assert j['stats']['received_value'] == 500 and j['stats']['outstanding'] == 500
    # Pay 300 → outstanding 200.
    tok = _csrf(c)
    c.post(f'/sales/suppliers/{sid}/pay', headers={'X-Requested-With': 'fetch'},
           data={'_csrf_token': tok, 'amount': 300, 'method': 'Bank Transfer'})
    j = c.get(f'/sales/suppliers/{sid}', headers={'X-Requested-With': 'fetch'}).get_json()
    assert j['stats']['paid'] == 300 and j['stats']['outstanding'] == 200


def test_purchasing_tables_bootstrap(app):
    from sqlalchemy import inspect
    with app.app_context():
        names = set(inspect(db.engine).get_table_names())
        for t in ('suppliers', 'purchase_orders', 'purchase_order_items', 'supplier_payments'):
            assert t in names
