"""Sales & Inventory routes (Stage 5).

Bursars manage a branch's products/stock and ring up sales. All views are
branch-scoped via utils.branch_scope.
"""

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, session, jsonify)
from sqlalchemy import func

from models import (db, Product, Sale, SaleItem, Student, StudentEnrollment,
                    ClassArmAssignment, SchoolClass, ClassArm)
from models.models_sales import PRODUCT_CATEGORIES, SALE_METHODS
from utils.access_control import login_required, filter_classes_for_user
from utils.branch_scope import scope_query, branch_for_new, can_access_branch
from utils import timeutil
from utils.helpers import get_active_term
from utils.search import like_term

sales_bp = Blueprint('sales', __name__, url_prefix='/sales')


def _wants_json():
    """The React UI posts via fetch with this header; reply JSON to it while
    keeping the classic flash+redirect for any plain form submit."""
    return request.headers.get('X-Requested-With') == 'fetch' or request.is_json


def _ok(message, redirect_url=None):
    if _wants_json():
        return jsonify({'ok': True, 'message': message, 'redirect': redirect_url})
    flash(message, 'success')
    return redirect(redirect_url or url_for('sales.dashboard'))


def _err(message, redirect_url=None):
    if _wants_json():
        return jsonify({'ok': False, 'error': message}), 400
    flash(message, 'error')
    return redirect(redirect_url or url_for('sales.dashboard'))


def _render(payload):
    """Render the shared sales React shell with an embedded payload."""
    from utils.spa import render_or_json
    return render_or_json('sales/app.html', 'sales_json', payload)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def _sale_row(s, with_when_year=False):
    fmt = '%d %b %Y %H:%M' if with_when_year else '%d %b %H:%M'
    return {
        'id': s.id, 'receipt_no': s.receipt_no, 'buyer': s.buyer,
        'payment_method': s.payment_method, 'total': s.total or 0,
        'item_count': s.items.count(),
        'when': s.created_at.strftime(fmt) if s.created_at else '',
        'receipt_url': url_for('sales.receipt', sale_id=s.id),
    }


@sales_bp.route('/')
@login_required
def dashboard():
    today = timeutil.today()
    todays = scope_query(Sale.query, Sale).filter(
        func.date(Sale.created_at) == today).all()
    today_total = sum(s.total or 0 for s in todays)
    products = scope_query(Product.query.filter_by(is_active=True), Product).all()
    low_stock = [p for p in products if p.low_stock]
    recent = (scope_query(Sale.query, Sale)
              .order_by(Sale.created_at.desc()).limit(8).all())
    return _render({
        'page': 'dashboard',
        'today_total': today_total, 'today_count': len(todays),
        'product_count': len(products),
        'low_stock': [{'name': p.name, 'category': p.category,
                       'stock_qty': p.stock_qty, 'reorder_level': p.reorder_level} for p in low_stock],
        'recent': [_sale_row(s) for s in recent],
        'urls': {'new_sale': url_for('sales.new_sale'), 'products': url_for('sales.products'),
                 'history': url_for('sales.history')},
    })


# ---------------------------------------------------------------------------
# Products / stock
# ---------------------------------------------------------------------------

@sales_bp.route('/products')
@login_required
def products():
    q = (request.args.get('q') or '').strip()
    query = scope_query(Product.query.filter_by(is_active=True), Product)
    if q:
        query = query.filter(Product.name.ilike(like_term(q), escape='\\'))
    rows = query.order_by(Product.category, Product.name).all()
    return _render({
        'page': 'products', 'q': q, 'categories': PRODUCT_CATEGORIES,
        'products': [{'id': p.id, 'name': p.name, 'sku': p.sku, 'category': p.category,
                      'unit_price': p.unit_price or 0, 'stock_qty': p.stock_qty,
                      'low_stock': bool(p.low_stock),
                      'restock_url': url_for('sales.restock', product_id=p.id)} for p in rows],
        'add_url': url_for('sales.add_product'),
        'urls': {'new_sale': url_for('sales.new_sale'), 'dashboard': url_for('sales.dashboard')},
    })


@sales_bp.route('/products/add', methods=['POST'])
@login_required
def add_product():
    name = (request.form.get('name') or '').strip()
    if not name:
        return _err('Product name is required.', url_for('sales.products'))
    db.session.add(Product(
        branch_id=branch_for_new(),
        name=name,
        category=request.form.get('category') or 'Other',
        sku=(request.form.get('sku') or '').strip() or None,
        unit_price=request.form.get('unit_price', type=float) or 0,
        cost_price=request.form.get('cost_price', type=float) or 0,
        stock_qty=request.form.get('stock_qty', type=int) or 0,
        reorder_level=request.form.get('reorder_level', type=int) or 0))
    db.session.commit()
    return _ok(f'Added "{name}".', url_for('sales.products'))


@sales_bp.route('/products/<int:product_id>/edit', methods=['POST'])
@login_required
def edit_product(product_id):
    p = db.get_or_404(Product, product_id)
    if not can_access_branch(p.branch_id):
        return _err('That product belongs to another branch.', url_for('sales.products'))
    p.name = (request.form.get('name') or p.name).strip()
    p.category = request.form.get('category') or p.category
    p.sku = (request.form.get('sku') or '').strip() or None
    p.unit_price = request.form.get('unit_price', type=float) or 0
    p.cost_price = request.form.get('cost_price', type=float) or 0
    p.reorder_level = request.form.get('reorder_level', type=int) or 0
    p.is_active = request.form.get('is_active') == 'on'
    db.session.commit()
    return _ok('Product updated.', url_for('sales.products'))


@sales_bp.route('/products/<int:product_id>/restock', methods=['POST'])
@login_required
def restock(product_id):
    p = db.get_or_404(Product, product_id)
    if not can_access_branch(p.branch_id):
        return _err('That product belongs to another branch.', url_for('sales.products'))
    qty = request.form.get('qty', type=int) or 0
    p.stock_qty = (p.stock_qty or 0) + qty
    db.session.commit()
    return _ok(f'Added {qty} to {p.name} (now {p.stock_qty}).', url_for('sales.products'))


# ---------------------------------------------------------------------------
# Selling
# ---------------------------------------------------------------------------

@sales_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_sale():
    if request.method == 'POST':
        product_ids = request.form.getlist('product_id', type=int)
        quantities = request.form.getlist('quantity', type=int)
        lines = []
        total = 0.0
        for pid, qty in zip(product_ids, quantities):
            if not pid or not qty or qty <= 0:
                continue
            p = db.session.get(Product, pid)
            if not p or not can_access_branch(p.branch_id):
                continue
            if qty > (p.stock_qty or 0):
                return _err(f'Only {p.stock_qty} of "{p.name}" in stock.', url_for('sales.new_sale'))
            line_total = round((p.unit_price or 0) * qty, 2)
            total += line_total
            lines.append((p, qty, line_total))
        if not lines:
            return _err('Add at least one item with a quantity.', url_for('sales.new_sale'))

        sale = Sale(
            branch_id=branch_for_new(),
            student_id=request.form.get('student_id', type=int) or None,
            customer_name=(request.form.get('customer_name') or '').strip() or None,
            payment_method=request.form.get('payment_method') or 'Cash',
            total=round(total, 2),
            amount_paid=request.form.get('amount_paid', type=float) or round(total, 2),
            sold_by=session.get('user') or session.get('username') or 'Bursar',
            notes=(request.form.get('notes') or '').strip() or None)
        # Stamp the revenue bucket (Bookshop / Uniform / …) from the line items so
        # the finance ledger categorises this sale when its after_insert fires —
        # the SaleItem rows don't exist in the DB yet at that point.
        from utils.finance_ledger import sale_category
        sale._ledger_category = sale_category([p.category for p, _, _ in lines])
        db.session.add(sale)
        db.session.flush()
        sale.receipt_no = f'SL{sale.id:05d}'
        for p, qty, line_total in lines:
            db.session.add(SaleItem(sale_id=sale.id, product_id=p.id,
                                    description=p.name, quantity=qty,
                                    unit_price=p.unit_price, line_total=line_total))
            p.stock_qty = (p.stock_qty or 0) - qty      # decrement stock
        db.session.commit()
        from utils.audit import log_action
        log_action('sales.sale', detail=f'{sale.total:g} ({len(lines)} item(s))',
                   target=sale)
        return _ok(f'Sale recorded — receipt {sale.receipt_no}.',
                   url_for('sales.receipt', sale_id=sale.id))

    products = scope_query(
        Product.query.filter_by(is_active=True), Product
    ).filter(Product.stock_qty > 0).order_by(Product.category, Product.name).all()
    classes, arms = _sale_class_arm_options()
    return _render({
        'page': 'new_sale', 'methods': SALE_METHODS,
        'submit_url': url_for('sales.new_sale'),
        'products': [{'id': p.id, 'name': p.name, 'category': p.category,
                      'unit_price': p.unit_price or 0, 'stock_qty': p.stock_qty} for p in products],
        # Large schools can't scroll one flat dropdown of every student — the
        # buyer is chosen by class (+ optional arm) then searched on demand.
        'classes': classes, 'arms': arms,
        'student_search_url': url_for('sales.api_students'),
        'urls': {'dashboard': url_for('sales.dashboard'), 'products': url_for('sales.products')},
    })


def _active_term_assignments():
    """ClassArmAssignments in the active term the current user may access."""
    active_term = get_active_term()
    if not active_term:
        return []
    return filter_classes_for_user(
        ClassArmAssignment.query.filter_by(term_id=active_term.id)
        .join(SchoolClass, ClassArmAssignment.class_id == SchoolClass.id).all())


def _sale_class_arm_options():
    """Distinct class + arm options for the sale buyer picker, scoped to what the
    user may see in the active term. Empty when no term is active."""
    assignments = _active_term_assignments()
    seen_c, seen_a, classes, arms = set(), set(), [], []
    for a in sorted(assignments, key=lambda x: ((x.school_class.level if x.school_class else 0),
                                                (x.school_class.name if x.school_class else ''))):
        if a.class_id not in seen_c and a.school_class:
            seen_c.add(a.class_id)
            classes.append({'id': a.class_id, 'name': a.school_class.name})
        arm = a.arm
        if arm and not arm.is_default and arm.id not in seen_a:
            seen_a.add(arm.id)
            arms.append({'id': arm.id, 'name': arm.name})
    arms.sort(key=lambda x: x['name'])
    return classes, arms


@sales_bp.route('/api/students')
@login_required
def api_students():
    """Students in a chosen class (+ optional arm) for the active term, matching
    an optional search — the buyer picker's on-demand lookup, so the sale form
    never ships every student. Branch/term/teacher scoped; capped."""
    class_id = request.args.get('class_id', type=int)
    arm_id = request.args.get('arm_id', type=int)
    q = (request.args.get('q') or '').strip()
    if not class_id:
        return jsonify({'students': []})
    assignments = [a for a in _active_term_assignments() if a.class_id == class_id
                   and (not arm_id or a.arm_id == arm_id)]
    aids = [a.id for a in assignments]
    if not aids:
        return jsonify({'students': []})
    query = (Student.query.filter_by(is_active=True)
             .join(StudentEnrollment, StudentEnrollment.student_id == Student.id)
             .filter(StudentEnrollment.class_arm_assignment_id.in_(aids),
                     StudentEnrollment.is_active == True))
    if q:
        term = like_term(q)
        query = query.filter(db.or_(
            Student.first_name.ilike(term, escape='\\'),
            Student.surname.ilike(term, escape='\\'),
            Student.middle_name.ilike(term, escape='\\'),
            Student.student_id.ilike(term, escape='\\')))
    rows = query.order_by(Student.surname, Student.first_name).limit(60).all()
    return jsonify({'students': [
        {'id': s.id, 'label': f'{s.full_name} ({s.student_id})',
         'student_id': s.student_id} for s in rows]})


@sales_bp.route('/history')
@login_required
def history():
    rows = (scope_query(Sale.query, Sale)
            .order_by(Sale.created_at.desc()).limit(300).all())
    total = sum(s.total or 0 for s in rows)
    return _render({
        'page': 'history', 'total': total,
        'sales': [_sale_row(s, with_when_year=True) for s in rows],
        'urls': {'dashboard': url_for('sales.dashboard')},
    })


@sales_bp.route('/receipt/<int:sale_id>')
@login_required
def receipt(sale_id):
    sale = db.get_or_404(Sale, sale_id)
    if not can_access_branch(sale.branch_id):
        flash('That sale belongs to another branch.', 'error')
        return redirect(url_for('sales.history'))
    return render_template('sales/receipt.html', sale=sale,
                           items=sale.items.all())
