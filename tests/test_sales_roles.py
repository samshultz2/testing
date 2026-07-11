"""Sales Phase 14 — granular storekeeper / procurement roles.

Sub-sections slice the Sales module (pos / catalogue / inventory / purchasing /
reports); two sensitive actions (approve a PO, sign off a stock count) are
explicit capabilities that broad module access does not imply.
"""
import json
from config import Config
from models import (db, User, Branch, Product, Supplier, PurchaseOrder,
                    PurchaseOrderItem, StockAudit, StockAuditItem)
from tests.conftest import login_token


def _make(app, username, perms):
    with app.app_context():
        if not User.query.filter_by(username=username).first():
            u = User(username=username, role='staff', scope='central', full_name=username)
            u.set_password('secret123'); u.set_permissions(perms)
            db.session.add(u); db.session.commit()


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return c


def _blocked(resp):
    return resp.status_code in (302, 303) or resp.status_code == 403


# --- sub-section scoping ----------------------------------------------------
def test_pos_role_cannot_reach_purchasing(app):
    _make(app, 'cashier1', {'sales.pos': 'edit'})
    c = _login(app, 'cashier1')
    assert c.get('/sales/new').status_code == 200            # POS granted
    assert _blocked(c.get('/sales/suppliers', follow_redirects=False))
    assert _blocked(c.get('/sales/purchases', follow_redirects=False))
    assert _blocked(c.get('/sales/audits', follow_redirects=False))


def test_storekeeper_role_reaches_inventory_only(app):
    _make(app, 'store1', {'sales.inventory': 'edit'})
    c = _login(app, 'store1')
    assert c.get('/sales/movements').status_code == 200
    assert c.get('/sales/audits').status_code == 200
    assert _blocked(c.get('/sales/new', follow_redirects=False))       # not POS
    assert _blocked(c.get('/sales/suppliers', follow_redirects=False))  # not purchasing


def test_view_only_inventory_blocks_write(app):
    _make(app, 'store2', {'sales.inventory': 'view'})
    c = _login(app, 'store2')
    with app.app_context():
        p = Product(branch_id=Branch.get_default().id, name='ZzRoleItem', category='Other',
                    unit_price=100, cost_price=40, stock_qty=10, is_active=True)
        db.session.add(p); db.session.commit(); pid = p.id
    r = c.post(f'/sales/products/{pid}/adjust', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': 'a' * 64, 'mode': 'count', 'counted': 3})
    assert _blocked(r)
    with app.app_context():
        assert db.session.get(Product, pid).stock_qty == 10       # unchanged


# --- capability: approving purchase orders ----------------------------------
def _make_po(app, tag):
    with app.app_context():
        sup = Supplier(branch_id=Branch.get_default().id, company_name=f'ZzSup{tag}')
        db.session.add(sup); db.session.flush()
        po = PurchaseOrder(branch_id=Branch.get_default().id, supplier_id=sup.id,
                           po_number=f'PO{tag}', status='Pending Approval')
        db.session.add(po); db.session.flush()
        db.session.add(PurchaseOrderItem(po_id=po.id, description='Thing', quantity=5, unit_cost=10))
        db.session.commit()
        return po.id


def test_purchasing_role_without_capability_cannot_approve(app):
    _make(app, 'buyer1', {'sales.purchasing': 'edit'})       # no approve_po
    c = _login(app, 'buyer1')
    poid = _make_po(app, 'CAP1')
    r = c.post(f'/sales/purchases/{poid}/approve', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': 'a' * 64})
    assert r.status_code == 400 or _blocked(r)
    with app.app_context():
        assert db.session.get(PurchaseOrder, poid).status == 'Pending Approval'


def test_purchasing_role_with_capability_can_approve(app):
    _make(app, 'buyer2', {'sales.purchasing': 'edit', 'sales.approve_po': 'edit'})
    c = _login(app, 'buyer2')
    poid = _make_po(app, 'CAP2')
    r = c.post(f'/sales/purchases/{poid}/approve', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': 'a' * 64})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        assert db.session.get(PurchaseOrder, poid).status == 'Approved'


# --- capability: signing off stock counts -----------------------------------
def _make_audit(app, tag):
    with app.app_context():
        p = Product(branch_id=Branch.get_default().id, name=f'ZzAud{tag}', category='Other',
                    unit_price=100, cost_price=40, stock_qty=10, is_active=True)
        db.session.add(p); db.session.flush()
        a = StockAudit(branch_id=Branch.get_default().id, reference=f'SA{tag}', status='Counting')
        db.session.add(a); db.session.flush()
        it = StockAuditItem(audit_id=a.id, product_id=p.id, product_name=p.name,
                            system_qty=10, unit_cost=40)
        db.session.add(it); db.session.commit()
        return a.id, it.id, p.id


def test_inventory_role_without_capability_cannot_sign_off(app):
    _make(app, 'store3', {'sales.inventory': 'edit'})        # no signoff_count
    c = _login(app, 'store3')
    aid, iid, pid = _make_audit(app, 'SO1')
    r = c.post(f'/sales/audits/{aid}/complete', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': 'a' * 64,
                     'counts': json.dumps([{'item_id': iid, 'counted_qty': 7}])})
    assert r.status_code == 400 or _blocked(r)
    with app.app_context():
        assert db.session.get(StockAudit, aid).status == 'Counting'
        assert db.session.get(Product, pid).stock_qty == 10


def test_inventory_role_with_capability_can_sign_off(app):
    _make(app, 'store4', {'sales.inventory': 'edit', 'sales.signoff_count': 'edit'})
    c = _login(app, 'store4')
    aid, iid, pid = _make_audit(app, 'SO2')
    r = c.post(f'/sales/audits/{aid}/complete', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': 'a' * 64,
                     'counts': json.dumps([{'item_id': iid, 'counted_qty': 7}])})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        assert db.session.get(StockAudit, aid).status == 'Completed'
        assert db.session.get(Product, pid).stock_qty == 7
