"""Changing an asset's status only moves units between buckets (total never
changes), units out on loan can't be moved or re-lent, and units back from
repair return to the usable pool."""
import uuid

from models import FixedAsset
from tests.test_sales_assets import _admin, _post


def _laptops(app, c, qty=30):
    name = 'ZzLaptops' + uuid.uuid4().hex[:5]
    assert _post(c, '/sales/assets/add', name=name, category='ICT Equipment', quantity=qty).get_json()['ok']
    with app.app_context():
        return FixedAsset.query.filter_by(name=name).first().id


def _bd(app, aid):
    with app.app_context():
        a = FixedAsset.query.get(aid)
        return {r['status']: r['quantity'] for r in a.status_breakdown}, a.quantity


def test_repair_round_trip_keeps_total(app):
    c = _admin(app); aid = _laptops(app, c)
    r = _post(c, f'/sales/assets/{aid}/move-status', from_status='In Use', to_status='Under Repair', quantity=12)
    assert r.get_json()['ok']
    assert _bd(app, aid) == ({'In Use': 18, 'Under Repair': 12}, 30)
    # repairs done: all 12 back into the pool
    assert _post(c, f'/sales/assets/{aid}/move-status', from_status='Under Repair', to_status='In Use', quantity=12).get_json()['ok']
    assert _bd(app, aid) == ({'In Use': 30}, 30)


def test_loaned_units_cannot_be_moved_or_relent(app):
    c = _admin(app); aid = _laptops(app, c, qty=31)
    assert _post(c, f'/sales/assets/{aid}/checkout', borrower='PTA', quantity=2).get_json()['ok']
    r = _post(c, f'/sales/assets/{aid}/move-status', from_status='In Use', to_status='Under Repair', quantity=31)
    assert not r.get_json()['ok'] and 'on loan' in r.get_json()['error']
    assert _post(c, f'/sales/assets/{aid}/move-status', from_status='In Use', to_status='Under Repair', quantity=29).get_json()['ok']
    # nothing usable left on site, so nothing more can be lent
    r = _post(c, f'/sales/assets/{aid}/checkout', borrower='Mr X', quantity=1)
    assert not r.get_json()['ok']
    d = c.get('/sales/assets', headers={'X-Requested-With': 'fetch', 'Accept': 'application/json'}).get_json()
    d = d.get('data', d)
    row = next(x for x in d['assets'] if x['id'] == aid)
    assert row['available_quantity'] == 0 and row['on_loan_quantity'] == 2 and row['active_quantity'] == 31
