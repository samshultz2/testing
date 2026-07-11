"""Sales & Inventory routes (Stage 5).

Bursars manage a branch's products/stock and ring up sales. All views are
branch-scoped via utils.branch_scope.
"""

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, session, jsonify)
from sqlalchemy import func

from models import (db, Product, Sale, SaleItem, StockMovement, Student,
                    StudentEnrollment, ClassArmAssignment, SchoolClass, ClassArm)
from models.models_sales import (PRODUCT_CATEGORIES, SALE_METHODS, CUSTOMER_TYPES,
                                 UNITS, STOCK_IN_REASONS, STOCK_OUT_REASONS)
from utils.access_control import login_required, filter_classes_for_user
from utils.branch_scope import scope_query, branch_for_new, can_access_branch
from utils import timeutil
from utils.helpers import get_active_term, parse_date
from utils.search import like_term
from utils.web_exports import xlsx_response

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
    out_stock = [p for p in products if p.out_of_stock]
    inv_value = round(sum(p.stock_value for p in products), 2)
    recent = (scope_query(Sale.query, Sale)
              .order_by(Sale.created_at.desc()).limit(8).all())
    return _render({
        'page': 'dashboard',
        'today_total': today_total, 'today_count': len(todays),
        'product_count': len(products), 'inventory_value': inv_value,
        'out_of_stock_count': len(out_stock),
        'low_stock': [{'name': p.name, 'category': p.category,
                       'stock_qty': p.stock_qty, 'reorder_level': p.reorder_level} for p in low_stock],
        'recent': [_sale_row(s) for s in recent],
        'urls': {'new_sale': url_for('sales.new_sale'), 'products': url_for('sales.products'),
                 'history': url_for('sales.history'), 'analytics': url_for('sales.analytics'),
                 'movements': url_for('sales.movements')},
    })


# ---------------------------------------------------------------------------
# Products / stock
# ---------------------------------------------------------------------------

_PRODUCT_STR = ('sku', 'barcode', 'brand', 'description', 'image_url', 'unit',
                'pack_size', 'preferred_supplier', 'storage_location', 'warranty_period')
_PRODUCT_FLOAT = ('unit_price', 'cost_price', 'discount_price', 'wholesale_price',
                  'staff_price', 'student_price', 'parent_price', 'vat_rate')
_PRODUCT_INT = ('stock_qty', 'reorder_level', 'opening_stock', 'max_stock', 'reorder_qty')
_PRODUCT_REQUIRED_NUM = {'unit_price', 'cost_price', 'stock_qty', 'reorder_level'}


def _apply_product_fields(p, form, is_new=False):
    """Copy the (many, mostly optional) product fields from a form onto a Product.
    Only keys present in the POST are touched, so a partial edit never blanks a
    field it didn't submit. Required numerics default to 0; the rest may be None."""
    from utils.security import strip_tags
    if 'name' in form:
        p.name = strip_tags(form.get('name') or '').strip() or p.name
    if 'category' in form:
        p.category = (form.get('category') or '').strip() or p.category or 'Other'
    for f in _PRODUCT_STR:
        if f in form:
            setattr(p, f, strip_tags(form.get(f) or '').strip() or None)
    for f in _PRODUCT_FLOAT:
        if f in form:
            v = form.get(f, type=float)
            setattr(p, f, (v or 0) if f in _PRODUCT_REQUIRED_NUM else v)
    for f in _PRODUCT_INT:
        if f in form:
            v = form.get(f, type=int)
            setattr(p, f, (v or 0) if f in _PRODUCT_REQUIRED_NUM else v)
    if 'taxable' in form:
        p.taxable = form.get('taxable') in ('on', 'true', '1', 'yes')
    if 'expiry_date' in form:
        p.expiry_date = parse_date(form.get('expiry_date'))
    if 'is_active' in form:
        p.is_active = form.get('is_active') in ('on', 'true', '1', 'yes')
    if is_new and p.opening_stock is None:
        p.opening_stock = p.stock_qty or 0


def _product_dict(p):
    """Full product detail for the list + edit form."""
    return {
        'id': p.id, 'name': p.name, 'category': p.category, 'sku': p.sku,
        'barcode': p.barcode, 'brand': p.brand, 'description': p.description,
        'unit_price': p.unit_price or 0, 'cost_price': p.cost_price or 0,
        'discount_price': p.discount_price, 'wholesale_price': p.wholesale_price,
        'staff_price': p.staff_price, 'student_price': p.student_price,
        'parent_price': p.parent_price,
        'stock_qty': p.stock_qty or 0, 'reorder_level': p.reorder_level or 0,
        'opening_stock': p.opening_stock, 'max_stock': p.max_stock, 'reorder_qty': p.reorder_qty,
        'unit': p.unit, 'pack_size': p.pack_size, 'taxable': bool(p.taxable),
        'vat_rate': p.vat_rate, 'preferred_supplier': p.preferred_supplier,
        'storage_location': p.storage_location,
        'expiry_date': p.expiry_date.isoformat() if p.expiry_date else '',
        'warranty_period': p.warranty_period, 'is_active': bool(p.is_active),
        'low_stock': bool(p.low_stock), 'out_of_stock': bool(p.out_of_stock),
        'stock_value': p.stock_value, 'margin_pct': p.margin_pct,
        'restock_url': url_for('sales.restock', product_id=p.id),
        'edit_url': url_for('sales.edit_product', product_id=p.id),
        'adjust_url': url_for('sales.adjust_stock', product_id=p.id),
    }


@sales_bp.route('/products')
@login_required
def products():
    q = (request.args.get('q') or '').strip()
    category = (request.args.get('category') or '').strip()
    stock = (request.args.get('stock') or '').strip()   # 'low' | 'out'
    query = scope_query(Product.query.filter_by(is_active=True), Product)
    if q:
        query = query.filter(db.or_(Product.name.ilike(like_term(q), escape='\\'),
                                    Product.sku.ilike(like_term(q), escape='\\'),
                                    Product.barcode.ilike(like_term(q), escape='\\')))
    if category:
        query = query.filter(Product.category == category)
    rows = query.order_by(Product.category, Product.name).all()
    if stock == 'low':
        rows = [p for p in rows if p.low_stock]
    elif stock == 'out':
        rows = [p for p in rows if p.out_of_stock]
    return _render({
        'page': 'products', 'q': q, 'category': category, 'stock': stock,
        'categories': PRODUCT_CATEGORIES, 'units': UNITS,
        'in_reasons': STOCK_IN_REASONS, 'out_reasons': STOCK_OUT_REASONS,
        'products': [_product_dict(p) for p in rows],
        'add_url': url_for('sales.add_product'),
        'urls': {'new_sale': url_for('sales.new_sale'), 'dashboard': url_for('sales.dashboard'),
                 'movements': url_for('sales.movements')},
    })


@sales_bp.route('/products/add', methods=['POST'])
@login_required
def add_product():
    name = (request.form.get('name') or '').strip()
    if not name:
        return _err('Product name is required.', url_for('sales.products'))
    p = Product(branch_id=branch_for_new())
    _apply_product_fields(p, request.form, is_new=True)
    db.session.add(p)
    db.session.commit()
    return _ok(f'Added "{p.name}".', url_for('sales.products'))


@sales_bp.route('/products/<int:product_id>/edit', methods=['POST'])
@login_required
def edit_product(product_id):
    p = db.get_or_404(Product, product_id)
    if not can_access_branch(p.branch_id):
        return _err('That product belongs to another branch.', url_for('sales.products'))
    _apply_product_fields(p, request.form)
    db.session.commit()
    return _ok('Product updated.', url_for('sales.products'))


def _record_movement(product, direction, quantity, reason, *, unit_cost=None,
                     reference=None, note=None, sale_id=None, apply=True):
    """Write one stock-ledger row and (by default) apply the change to the
    product's on-hand quantity. Pass apply=False when the caller has already
    adjusted stock (e.g. the sale loop). Returns the StockMovement."""
    quantity = abs(int(quantity or 0))
    if apply:
        product.stock_qty = (product.stock_qty or 0) + (quantity if direction == 'in' else -quantity)
    mv = StockMovement(
        branch_id=product.branch_id, product_id=product.id, direction=direction,
        reason=reason, quantity=quantity, qty_after=product.stock_qty,
        unit_cost=unit_cost, reference=reference, note=note, sale_id=sale_id,
        performed_by=session.get('user') or session.get('username') or 'System')
    db.session.add(mv)
    return mv


@sales_bp.route('/products/<int:product_id>/restock', methods=['POST'])
@login_required
def restock(product_id):
    p = db.get_or_404(Product, product_id)
    if not can_access_branch(p.branch_id):
        return _err('That product belongs to another branch.', url_for('sales.products'))
    qty = request.form.get('qty', type=int) or 0
    if qty <= 0:
        return _err('Enter a quantity to add.', url_for('sales.products'))
    _record_movement(p, 'in', qty, request.form.get('reason') or 'Stock In (Purchase/GRN)',
                     unit_cost=request.form.get('unit_cost', type=float),
                     reference=(request.form.get('reference') or '').strip() or None)
    db.session.commit()
    return _ok(f'Added {qty} to {p.name} (now {p.stock_qty}).', url_for('sales.products'))


@sales_bp.route('/products/<int:product_id>/adjust', methods=['POST'])
@login_required
def adjust_stock(product_id):
    """Record a manual stock movement (issue, usage, damage, return, transfer,
    correction…) or set an exact physical count. Every change is ledgered."""
    p = db.get_or_404(Product, product_id)
    if not can_access_branch(p.branch_id):
        return _err('That product belongs to another branch.', url_for('sales.products'))
    mode = request.form.get('mode') or 'move'
    note = (request.form.get('note') or '').strip() or None
    reference = (request.form.get('reference') or '').strip() or None

    if mode == 'count':
        counted = request.form.get('counted', type=int)
        if counted is None or counted < 0:
            return _err('Enter the counted quantity.', url_for('sales.products'))
        delta = counted - (p.stock_qty or 0)
        if delta == 0:
            return _ok('Count matches — no change.', url_for('sales.products'))
        p.stock_qty = counted
        _record_movement(p, 'in' if delta > 0 else 'out', abs(delta),
                         'Physical Stock Count', note=note, reference=reference, apply=False)
        db.session.commit()
        return _ok(f'Stock count set to {counted} for {p.name}.', url_for('sales.products'))

    direction = request.form.get('direction')
    reason = request.form.get('reason') or ''
    qty = request.form.get('quantity', type=int) or 0
    if direction not in ('in', 'out') or qty <= 0:
        return _err('Choose a direction and quantity.', url_for('sales.products'))
    allowed = STOCK_IN_REASONS if direction == 'in' else STOCK_OUT_REASONS
    if reason not in allowed:
        return _err('Invalid reason for this movement.', url_for('sales.products'))
    if direction == 'out' and qty > (p.stock_qty or 0):
        return _err(f'Only {p.stock_qty} in stock — cannot remove {qty}.', url_for('sales.products'))
    _record_movement(p, direction, qty, reason,
                     unit_cost=request.form.get('unit_cost', type=float),
                     reference=reference, note=note)
    db.session.commit()
    return _ok(f'Recorded {qty} {direction} for {p.name} (now {p.stock_qty}).',
               url_for('sales.products'))


@sales_bp.route('/movements')
@login_required
def movements():
    """The inventory movement ledger — every stock change, filterable."""
    a = request.args
    product_id = a.get('product_id', type=int)
    direction = (a.get('direction') or '').strip()
    reason = (a.get('reason') or '').strip()
    from_d = parse_date(a.get('from'))
    to_d = parse_date(a.get('to'))
    query = scope_query(StockMovement.query, StockMovement)
    if product_id:
        query = query.filter(StockMovement.product_id == product_id)
    if direction in ('in', 'out'):
        query = query.filter(StockMovement.direction == direction)
    if reason:
        query = query.filter(StockMovement.reason == reason)
    if from_d:
        query = query.filter(func.date(StockMovement.created_at) >= from_d)
    if to_d:
        query = query.filter(func.date(StockMovement.created_at) <= to_d)
    rows = query.order_by(StockMovement.created_at.desc()).limit(500).all()
    name_by_id = {p.id: p.name for p in scope_query(Product.query, Product).all()}
    total_in = sum(m.quantity for m in rows if m.direction == 'in')
    total_out = sum(m.quantity for m in rows if m.direction == 'out')
    return _render({
        'page': 'movements',
        'movements': [{'id': m.id, 'product': name_by_id.get(m.product_id, '—'),
                       'direction': m.direction, 'reason': m.reason,
                       'quantity': m.quantity, 'qty_after': m.qty_after,
                       'unit_cost': m.unit_cost, 'reference': m.reference,
                       'note': m.note, 'by': m.performed_by,
                       'when': m.created_at.strftime('%d %b %Y %H:%M') if m.created_at else ''}
                      for m in rows],
        'summary': {'count': len(rows), 'total_in': total_in, 'total_out': total_out},
        'options': {'products': [{'id': p.id, 'name': p.name} for p in scope_query(
            Product.query, Product).order_by(Product.name).all()],
            'reasons': STOCK_IN_REASONS + STOCK_OUT_REASONS + ['Sale', 'Physical Stock Count']},
        'applied': {'product_id': product_id or '', 'direction': direction,
                    'reason': reason, 'from': a.get('from', ''), 'to': a.get('to', '')},
        'self_url': url_for('sales.movements'),
        'urls': {'dashboard': url_for('sales.dashboard'), 'products': url_for('sales.products')},
    })


# ---------------------------------------------------------------------------
# Selling
# ---------------------------------------------------------------------------

@sales_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_sale():
    if request.method == 'POST':
        student_id = request.form.get('student_id', type=int) or None
        # Buyer type drives tiered pricing. A chosen student is always 'Student';
        # otherwise use the submitted type (Staff/Parent/Visitor/Walk-in).
        customer_type = (request.form.get('customer_type') or '').strip() or None
        if student_id:
            customer_type = 'Student'
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
            unit = p.price_for(customer_type)              # tiered price
            line_total = round((unit or 0) * qty, 2)
            total += line_total
            lines.append((p, qty, unit, line_total))
        if not lines:
            return _err('Add at least one item with a quantity.', url_for('sales.new_sale'))

        sale = Sale(
            branch_id=branch_for_new(),
            student_id=student_id,
            customer_name=(request.form.get('customer_name') or '').strip() or None,
            customer_type=customer_type,
            payment_method=request.form.get('payment_method') or 'Cash',
            total=round(total, 2),
            amount_paid=request.form.get('amount_paid', type=float) or round(total, 2),
            sold_by=session.get('user') or session.get('username') or 'Bursar',
            notes=(request.form.get('notes') or '').strip() or None)
        # Stamp the revenue bucket (Bookshop / Uniform / …) from the line items so
        # the finance ledger categorises this sale when its after_insert fires —
        # the SaleItem rows don't exist in the DB yet at that point.
        from utils.finance_ledger import sale_category
        sale._ledger_category = sale_category([p.category for p, _, _, _ in lines])
        db.session.add(sale)
        db.session.flush()
        sale.receipt_no = f'SL{sale.id:05d}'
        for p, qty, unit, line_total in lines:
            db.session.add(SaleItem(sale_id=sale.id, product_id=p.id,
                                    description=p.name, quantity=qty,
                                    unit_price=unit, line_total=line_total))
            p.stock_qty = (p.stock_qty or 0) - qty      # decrement stock
            # Ledger the outward movement (stock already decremented above).
            _record_movement(p, 'out', qty, 'Sale', sale_id=sale.id,
                             reference=sale.receipt_no, apply=False)
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
        'page': 'new_sale', 'methods': SALE_METHODS, 'customer_types': CUSTOMER_TYPES,
        'submit_url': url_for('sales.new_sale'),
        # Tier prices ride along so the form can price the cart live per buyer type.
        'products': [{'id': p.id, 'name': p.name, 'category': p.category,
                      'unit_price': p.unit_price or 0, 'stock_qty': p.stock_qty,
                      'student_price': p.student_price, 'staff_price': p.staff_price,
                      'parent_price': p.parent_price} for p in products],
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


def _history_context(limit=500):
    """Filtered, detailed sales history shared by the page and the export. Reads
    from/to, method, cashier, buyer_type, product_id, category and a text query
    from request.args; returns (rows, summary, options, applied)."""
    from datetime import timedelta
    from collections import defaultdict
    a = request.args
    to_d = parse_date(a.get('to'))
    from_d = parse_date(a.get('from'))
    method = (a.get('method') or '').strip()
    cashier = (a.get('cashier') or '').strip()
    buyer_type = (a.get('buyer_type') or '').strip()   # 'student' | 'other'
    product_id = a.get('product_id', type=int)
    category = (a.get('category') or '').strip()
    q = (a.get('q') or '').strip()

    query = scope_query(Sale.query, Sale)
    if from_d:
        query = query.filter(func.date(Sale.created_at) >= from_d)
    if to_d:
        query = query.filter(func.date(Sale.created_at) <= to_d)
    if method:
        query = query.filter(Sale.payment_method == method)
    if cashier:
        query = query.filter(Sale.sold_by == cashier)
    if buyer_type == 'student':
        query = query.filter(Sale.student_id.isnot(None))
    elif buyer_type == 'other':
        query = query.filter(Sale.student_id.is_(None))
    if q:
        term = like_term(q)
        query = query.filter(db.or_(Sale.receipt_no.ilike(term, escape='\\'),
                                    Sale.customer_name.ilike(term, escape='\\')))
    # Product / category filters compose via a SaleItem subquery.
    if product_id or category:
        sub = db.session.query(SaleItem.sale_id)
        if category:
            sub = sub.join(Product, SaleItem.product_id == Product.id).filter(Product.category == category)
        if product_id:
            sub = sub.filter(SaleItem.product_id == product_id)
        query = query.filter(Sale.id.in_(sub))

    sales = query.order_by(Sale.created_at.desc()).limit(limit).all()
    sale_ids = [s.id for s in sales]

    # Batch line items + buyer placements (no N+1).
    items_by_sale = defaultdict(list)
    if sale_ids:
        for it in SaleItem.query.filter(SaleItem.sale_id.in_(sale_ids)).all():
            items_by_sale[it.sale_id].append(it)
    placement = {}
    active_term = get_active_term()
    stud_ids = [s.student_id for s in sales if s.student_id]
    if stud_ids and active_term:
        enr = (db.session.query(StudentEnrollment.student_id, SchoolClass.name,
                                ClassArm.name, ClassArm.is_default)
               .join(ClassArmAssignment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
               .join(SchoolClass, ClassArmAssignment.class_id == SchoolClass.id)
               .join(ClassArm, ClassArmAssignment.arm_id == ClassArm.id)
               .filter(StudentEnrollment.student_id.in_(stud_ids),
                       StudentEnrollment.is_active == True,
                       ClassArmAssignment.term_id == active_term.id).all())
        for sid, cname, aname, adef in enr:
            placement[sid] = f'{cname}{"" if adef else " " + (aname or "")}'.strip()

    rows = []
    for s in sales:
        its = items_by_sale.get(s.id, [])
        paid = s.amount_paid if s.amount_paid is not None else (s.total or 0)
        rows.append({
            'id': s.id, 'receipt_no': s.receipt_no, 'buyer': s.buyer,
            'buyer_type': 'Student' if s.student_id else 'Staff / Walk-in',
            'class_arm': placement.get(s.student_id, '') if s.student_id else '',
            'cashier': s.sold_by or '', 'payment_method': s.payment_method or 'Cash',
            'total': round(s.total or 0, 2), 'amount_paid': round(paid, 2),
            'balance': round((s.total or 0) - paid, 2),
            'item_count': len(its),
            'items': [{'name': it.description or '', 'quantity': it.quantity or 0,
                       'unit_price': round(it.unit_price or 0, 2),
                       'line_total': round(it.line_total or 0, 2)} for it in its],
            'when': s.created_at.strftime('%d %b %Y %H:%M') if s.created_at else '',
            'receipt_url': url_for('sales.receipt', sale_id=s.id),
        })
    summary = {'count': len(rows), 'revenue': round(sum(r['total'] for r in rows), 2),
               'units': sum(sum(i['quantity'] for i in r['items']) for r in rows)}
    cashiers = sorted({r[0] for r in scope_query(
        db.session.query(Sale.sold_by).distinct(), Sale).all() if r[0]})
    options = {'methods': SALE_METHODS, 'categories': list(PRODUCT_CATEGORIES),
               'cashiers': cashiers,
               'products': [{'id': p.id, 'name': p.name} for p in scope_query(
                   Product.query, Product).order_by(Product.name).all()]}
    applied = {'from': a.get('from', ''), 'to': a.get('to', ''), 'method': method,
               'cashier': cashier, 'buyer_type': buyer_type,
               'product_id': product_id or '', 'category': category, 'q': q}
    return rows, summary, options, applied


@sales_bp.route('/history')
@login_required
def history():
    rows, summary, options, applied = _history_context()
    return _render({
        'page': 'history', 'total': summary['revenue'], 'summary': summary,
        'sales': rows, 'options': options, 'applied': applied,
        'self_url': url_for('sales.history'),
        'export_url': url_for('sales.history_export'),
        'urls': {'dashboard': url_for('sales.dashboard'),
                 'analytics': url_for('sales.analytics')},
    })


@sales_bp.route('/history/export')
@login_required
def history_export():
    """Export the filtered sales history as CSV or Excel (one row per sale)."""
    fmt = (request.args.get('format') or 'csv').lower()
    rows, _summary, _opts, _applied = _history_context(limit=5000)
    headers = ['Receipt', 'Date', 'Buyer', 'Type', 'Class/Arm', 'Cashier',
               'Method', 'Items', 'Total', 'Paid', 'Balance']

    def _record(r):
        return [r['receipt_no'], r['when'], r['buyer'], r['buyer_type'], r['class_arm'],
                r['cashier'], r['payment_method'], r['item_count'],
                r['total'], r['amount_paid'], r['balance']]

    if fmt in ('excel', 'xlsx'):
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active; ws.title = 'Sales'
        ws.append(headers)
        for r in rows:
            ws.append(_record(r))
        return xlsx_response(wb, 'sales_history.xlsx')
    # CSV (default)
    import csv
    import io
    from flask import Response
    out = io.StringIO(); w = csv.writer(out)
    w.writerow(headers)
    for r in rows:
        w.writerow(_record(r))
    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=sales_history.csv'})


@sales_bp.route('/analytics')
@login_required
def analytics():
    """Sales analytics for management: revenue / units / profit over a date
    range, broken down by category, product, payment method and cashier, with a
    daily/weekly trend — plus a product drill-down showing how many students in
    each class/arm bought a chosen product. Branch-scoped."""
    from datetime import timedelta
    from collections import defaultdict

    to_d = parse_date(request.args.get('to')) or timeutil.today()
    from_d = parse_date(request.args.get('from')) or (to_d - timedelta(days=29))
    if from_d > to_d:
        from_d, to_d = to_d, from_d
    product_id = request.args.get('product_id', type=int)

    sales = (scope_query(Sale.query, Sale)
             .filter(func.date(Sale.created_at) >= from_d,
                     func.date(Sale.created_at) <= to_d).all())
    sale_ids = [s.id for s in sales]
    items = []
    if sale_ids:
        items = (db.session.query(SaleItem, Product)
                 .outerjoin(Product, SaleItem.product_id == Product.id)
                 .filter(SaleItem.sale_id.in_(sale_ids)).all())

    revenue = sum(s.total or 0 for s in sales)
    units = sum((it.quantity or 0) for it, _ in items)
    cogs = sum((it.quantity or 0) * ((p.cost_price or 0) if p else 0) for it, p in items)
    count = len(sales)

    cat = defaultdict(lambda: {'units': 0, 'revenue': 0.0})
    prod = defaultdict(lambda: {'units': 0, 'revenue': 0.0, 'name': ''})
    for it, p in items:
        c = (p.category if p else None) or 'Other'
        cat[c]['units'] += it.quantity or 0
        cat[c]['revenue'] += it.line_total or 0
        key = it.product_id or f'desc:{it.description}'
        prod[key]['units'] += it.quantity or 0
        prod[key]['revenue'] += it.line_total or 0
        prod[key]['name'] = (p.name if p else None) or it.description or 'Unknown'

    method = defaultdict(lambda: {'count': 0, 'revenue': 0.0})
    cashier = defaultdict(lambda: {'count': 0, 'revenue': 0.0})
    trend_map = defaultdict(float)
    for s in sales:
        method[s.payment_method or 'Cash']['count'] += 1
        method[s.payment_method or 'Cash']['revenue'] += s.total or 0
        cashier[s.sold_by or 'Unknown']['count'] += 1
        cashier[s.sold_by or 'Unknown']['revenue'] += s.total or 0
        if s.created_at:
            trend_map[s.created_at.date()] += s.total or 0

    # Trend: daily, or weekly buckets when the range is long, so the chart stays
    # readable.
    span = (to_d - from_d).days + 1
    trend = []
    if span > 62:
        wk_start = from_d
        while wk_start <= to_d:
            wk_end = min(wk_start + timedelta(days=6), to_d)
            rv = sum(v for dd, v in trend_map.items() if wk_start <= dd <= wk_end)
            trend.append({'label': wk_start.strftime('%d %b'), 'revenue': round(rv, 2)})
            wk_start += timedelta(days=7)
    else:
        dcur = from_d
        while dcur <= to_d:
            trend.append({'label': dcur.strftime('%d %b'), 'revenue': round(trend_map.get(dcur, 0.0), 2)})
            dcur += timedelta(days=1)

    def _pack(dmap, label_key='label'):
        out = [{label_key: k, **v} for k, v in dmap.items()]
        out.sort(key=lambda x: x.get('revenue', 0), reverse=True)
        for r in out:
            r['revenue'] = round(r['revenue'], 2)
        return out

    top_products = sorted(prod.values(), key=lambda x: x['revenue'], reverse=True)[:10]
    for r in top_products:
        r['revenue'] = round(r['revenue'], 2)

    drill = _product_drilldown(sale_ids, product_id) if product_id else None
    products_list = [{'id': p.id, 'name': p.name} for p in scope_query(
        Product.query, Product).order_by(Product.name).all()]

    return _render({
        'page': 'analytics',
        'from': from_d.isoformat(), 'to': to_d.isoformat(),
        'summary': {'revenue': round(revenue, 2), 'count': count, 'units': units,
                    'profit': round(revenue - cogs, 2),
                    'avg_sale': round(revenue / count, 2) if count else 0.0},
        'by_category': _pack(cat), 'top_products': top_products,
        'by_method': _pack(method), 'by_cashier': _pack(cashier),
        'trend': trend,
        'products': products_list, 'product_id': product_id, 'drill': drill,
        'self_url': url_for('sales.analytics'),
        'urls': {'dashboard': url_for('sales.dashboard'), 'history': url_for('sales.history')},
    })


def _product_drilldown(sale_ids, product_id):
    """For a chosen product, how many students in each class/arm bought it (and
    units/revenue), using each buyer's current active enrolment for attribution.
    Non-student buyers (staff/parent/walk-in) are summarised separately."""
    from collections import defaultdict
    if not sale_ids:
        return {'product_id': product_id, 'rows': [], 'total_units': 0,
                'total_students': 0, 'non_student_units': 0}
    rows = (db.session.query(SaleItem, Sale)
            .join(Sale, SaleItem.sale_id == Sale.id)
            .filter(SaleItem.sale_id.in_(sale_ids),
                    SaleItem.product_id == product_id).all())
    active_term = get_active_term()
    student_ids = [sale.student_id for _it, sale in rows if sale.student_id]
    placement = {}
    if student_ids and active_term:
        enr = (db.session.query(StudentEnrollment.student_id, SchoolClass.name,
                                ClassArm.name, ClassArm.is_default)
               .join(ClassArmAssignment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
               .join(SchoolClass, ClassArmAssignment.class_id == SchoolClass.id)
               .join(ClassArm, ClassArmAssignment.arm_id == ClassArm.id)
               .filter(StudentEnrollment.student_id.in_(student_ids),
                       StudentEnrollment.is_active == True,
                       ClassArmAssignment.term_id == active_term.id).all())
        for sid, cname, aname, adef in enr:
            placement[sid] = (cname, '' if adef else (aname or ''))
    by_class = defaultdict(lambda: {'students': set(), 'units': 0, 'revenue': 0.0})
    total_units = 0
    total_students = set()
    non_student_units = 0
    for it, sale in rows:
        total_units += it.quantity or 0
        if sale.student_id and sale.student_id in placement:
            cname, aname = placement[sale.student_id]
            key = f'{cname} {aname}'.strip()
            by_class[key]['students'].add(sale.student_id)
            by_class[key]['units'] += it.quantity or 0
            by_class[key]['revenue'] += it.line_total or 0
            total_students.add(sale.student_id)
        else:
            non_student_units += it.quantity or 0
    out = [{'label': k, 'students': len(v['students']), 'units': v['units'],
            'revenue': round(v['revenue'], 2)} for k, v in by_class.items()]
    out.sort(key=lambda x: x['units'], reverse=True)
    return {'product_id': product_id, 'rows': out, 'total_units': total_units,
            'total_students': len(total_students), 'non_student_units': non_student_units}


@sales_bp.route('/receipt/<int:sale_id>')
@login_required
def receipt(sale_id):
    sale = db.get_or_404(Sale, sale_id)
    if not can_access_branch(sale.branch_id):
        flash('That sale belongs to another branch.', 'error')
        return redirect(url_for('sales.history'))
    return render_template('sales/receipt.html', sale=sale,
                           items=sale.items.all())
