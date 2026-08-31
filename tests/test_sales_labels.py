"""Sales Phase 13 — barcode label generation & printing."""
import pytest
from config import Config
from models import db, Branch, Product
from tests.conftest import login_token
from utils.barcode_svg import code128_svg, encodable, _symbols


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return c


def _product(app, name, tag, barcode=None, price=500):
    with app.app_context():
        p = Product(branch_id=Branch.get_default().id, name=f'{name}{tag}',
                    category=f'ZzLbl{tag}', unit_price=price, cost_price=200,
                    stock_qty=10, is_active=True, barcode=barcode)
        db.session.add(p); db.session.commit()
        return p.id


# --- encoder ---------------------------------------------------------------
def test_encoder_structure_and_checksum():
    # start B (104), payload, mod-103 checksum, stop (106)
    assert _symbols('12345') == [104, 17, 18, 19, 20, 21, 90, 106]
    svg = code128_svg('ABC-123')
    assert svg.startswith('<svg') and svg.rstrip().endswith('</svg>')
    assert '<rect' in svg and 'Barcode ABC-123' in svg


def test_encodable_rules():
    assert encodable('SKU-001') and encodable('9781234567897')
    assert not encodable('') and not encodable('café')


def test_encoder_rejects_non_ascii():
    with pytest.raises(ValueError):
        code128_svg('naïve')


def test_encoder_escapes_special_chars():
    # a quote in the data must not break the SVG attributes/text
    svg = code128_svg('A"B')
    assert '"A"B"' not in svg and '&#34;' in svg


# --- generate barcodes -----------------------------------------------------
def test_generate_barcodes_fills_missing_only(app):
    c = _admin(app)
    without = _product(app, 'NoCode', 'GEN')
    with_code = _product(app, 'HasCode', 'GEN', barcode='EXISTING9')
    r = c.post('/sales/products/generate-barcodes', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': 'a' * 64, 'category': f'ZzLblGEN'})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        assert db.session.get(Product, without).barcode == f'PB{without:06d}'
        assert db.session.get(Product, with_code).barcode == 'EXISTING9'   # untouched


# --- label sheet -----------------------------------------------------------
def test_labels_render_with_barcode_and_price(app):
    c = _admin(app)
    _product(app, 'Marker', 'REN', barcode='555001', price=750)
    r = c.get('/sales/products/labels?category=ZzLblREN')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'MarkerREN' in body and '<svg' in body and '555001' in body
    assert '₦750' in body or '750' in body


def test_labels_copies_repeat(app):
    c = _admin(app)
    _product(app, 'Eraser', 'CP', barcode='777')
    body = c.get('/sales/products/labels?category=ZzLblCP&copies=3').get_data(as_text=True)
    assert body.count('EraserCP') == 3


def test_labels_fallback_code_for_missing_barcode(app):
    c = _admin(app)
    pid = _product(app, 'Chalk', 'FB')            # no barcode
    body = c.get('/sales/products/labels?category=ZzLblFB').get_data(as_text=True)
    assert f'PB{pid:06d}' in body                 # internal code used on the label
