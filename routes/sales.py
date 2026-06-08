"""Sales & Inventory routes (Stage 5).

Bursars manage a branch's products/stock and ring up sales. All views are
branch-scoped via utils.branch_scope.
"""
from datetime import date

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, session)
from sqlalchemy import func

from models import db, Product, Sale, SaleItem, Student
from models.models_sales import PRODUCT_CATEGORIES, SALE_METHODS
from utils.access_control import login_required
from utils.branch_scope import scope_query, branch_for_new, can_access_branch
from utils import timeutil

sales_bp = Blueprint('sales', __name__, url_prefix='/sales')


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

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
    return render_template('sales/dashboard.html',
        today_total=today_total, today_count=len(todays),
        product_count=len(products), low_stock=low_stock, recent=recent)


# ---------------------------------------------------------------------------
# Products / stock
# ---------------------------------------------------------------------------

@sales_bp.route('/products')
@login_required
def products():
    q = (request.args.get('q') or '').strip()
    query = scope_query(Product.query.filter_by(is_active=True), Product)
    if q:
        query = query.filter(Product.name.ilike(f'%{q}%'))
    rows = query.order_by(Product.category, Product.name).all()
    return render_template('sales/products.html', products=rows, q=q,
                           categories=PRODUCT_CATEGORIES)


@sales_bp.route('/products/add', methods=['POST'])
@login_required
def add_product():
    name = (request.form.get('name') or '').strip()
    if not name:
        flash('Product name is required.', 'error')
        return redirect(url_for('sales.products'))
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
    flash(f'Added "{name}".', 'success')
    return redirect(url_for('sales.products'))


@sales_bp.route('/products/<int:product_id>/edit', methods=['POST'])
@login_required
def edit_product(product_id):
    p = Product.query.get_or_404(product_id)
    if not can_access_branch(p.branch_id):
        flash('That product belongs to another branch.', 'error')
        return redirect(url_for('sales.products'))
    p.name = (request.form.get('name') or p.name).strip()
    p.category = request.form.get('category') or p.category
    p.sku = (request.form.get('sku') or '').strip() or None
    p.unit_price = request.form.get('unit_price', type=float) or 0
    p.cost_price = request.form.get('cost_price', type=float) or 0
    p.reorder_level = request.form.get('reorder_level', type=int) or 0
    p.is_active = request.form.get('is_active') == 'on'
    db.session.commit()
    flash('Product updated.', 'success')
    return redirect(url_for('sales.products'))


@sales_bp.route('/products/<int:product_id>/restock', methods=['POST'])
@login_required
def restock(product_id):
    p = Product.query.get_or_404(product_id)
    if not can_access_branch(p.branch_id):
        flash('That product belongs to another branch.', 'error')
        return redirect(url_for('sales.products'))
    qty = request.form.get('qty', type=int) or 0
    p.stock_qty = (p.stock_qty or 0) + qty
    db.session.commit()
    flash(f'Added {qty} to {p.name} (now {p.stock_qty}).', 'success')
    return redirect(url_for('sales.products'))


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
            p = Product.query.get(pid)
            if not p or not can_access_branch(p.branch_id):
                continue
            if qty > (p.stock_qty or 0):
                flash(f'Only {p.stock_qty} of "{p.name}" in stock.', 'error')
                return redirect(url_for('sales.new_sale'))
            line_total = round((p.unit_price or 0) * qty, 2)
            total += line_total
            lines.append((p, qty, line_total))
        if not lines:
            flash('Add at least one item with a quantity.', 'error')
            return redirect(url_for('sales.new_sale'))

        sale = Sale(
            branch_id=branch_for_new(),
            student_id=request.form.get('student_id', type=int) or None,
            customer_name=(request.form.get('customer_name') or '').strip() or None,
            payment_method=request.form.get('payment_method') or 'Cash',
            total=round(total, 2),
            amount_paid=request.form.get('amount_paid', type=float) or round(total, 2),
            sold_by=session.get('user') or session.get('username') or 'Bursar',
            notes=(request.form.get('notes') or '').strip() or None)
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
        flash(f'Sale recorded — receipt {sale.receipt_no}.', 'success')
        return redirect(url_for('sales.receipt', sale_id=sale.id))

    products = scope_query(
        Product.query.filter_by(is_active=True), Product
    ).filter(Product.stock_qty > 0).order_by(Product.category, Product.name).all()
    students = scope_query(Student.query.filter_by(is_active=True), Student) \
        .order_by(Student.surname, Student.first_name).all()
    return render_template('sales/new_sale.html', products=products,
                           students=students, methods=SALE_METHODS)


@sales_bp.route('/history')
@login_required
def history():
    rows = (scope_query(Sale.query, Sale)
            .order_by(Sale.created_at.desc()).limit(300).all())
    total = sum(s.total or 0 for s in rows)
    return render_template('sales/history.html', sales=rows, total=total)


@sales_bp.route('/receipt/<int:sale_id>')
@login_required
def receipt(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    if not can_access_branch(sale.branch_id):
        flash('That sale belongs to another branch.', 'error')
        return redirect(url_for('sales.history'))
    return render_template('sales/receipt.html', sale=sale,
                           items=sale.items.all())
