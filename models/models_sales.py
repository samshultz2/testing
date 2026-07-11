"""Sales & Inventory (Stage 5).

Bursars sell items (textbooks, workbooks, notebooks, uniforms…) and track stock.
Everything is branch-scoped: each branch has its own products and sales.
"""
from models.models import db, local_now

# The catalogue categories offered in the UI. Free-text is still accepted (so
# legacy values like 'Textbook' and any custom category keep working); this is
# just the pick-list. Kept broad to cover a school store's full range.
PRODUCT_CATEGORIES = [
    'Academic Materials', 'Textbooks', 'Exercise Books', 'Stationery', 'Uniforms',
    'Sports Wear', 'School Bags', 'ICT Equipment', 'Office Supplies',
    'Cleaning Materials', 'Laboratory Materials', 'Medical Supplies',
    'Hostel Supplies', 'Kitchen Supplies', 'Transport Supplies', 'Other',
]
SALE_METHODS = ['Cash', 'Transfer', 'POS']
# Buyer types drive tiered pricing + sales segmentation.
CUSTOMER_TYPES = ['Student', 'Staff', 'Parent', 'Visitor', 'Walk-in']

# Stock movement reasons, grouped by direction. 'Sale' and 'Physical Stock Count'
# are recorded by the system, not chosen from the manual-adjustment menu.
STOCK_IN_REASONS = ['Stock In (Purchase/GRN)', 'Customer Return', 'Transfer In',
                    'Found Stock', 'Opening Stock', 'Correction (Increase)']
STOCK_OUT_REASONS = ['Issue / Stock Out', 'Classroom Use', 'Laboratory Use',
                     'Office Use', 'Hostel Use', 'Kitchen Use', 'Damage', 'Theft',
                     'Donation', 'Expired', 'Supplier Return', 'Transfer Out',
                     'Correction (Decrease)', 'Loss', 'Converted to Fixed Asset']
UNITS = ['Piece', 'Pack', 'Ream', 'Dozen', 'Box', 'Carton', 'Set', 'Pair',
         'Bottle', 'Litre', 'Kg', 'Roll']


class Product(db.Model):
    __tablename__ = 'sales_products'

    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(40), default='Other')
    sku = db.Column(db.String(40))
    unit_price = db.Column(db.Float, default=0)        # selling price
    cost_price = db.Column(db.Float, default=0)        # optional, for margin
    stock_qty = db.Column(db.Integer, default=0)
    reorder_level = db.Column(db.Integer, default=0)   # low-stock / min threshold
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)

    # --- Optional catalogue detail (all nullable; additive) -----------------
    barcode = db.Column(db.String(60), index=True)
    brand = db.Column(db.String(80))
    description = db.Column(db.Text)
    image_url = db.Column(db.String(255))
    # Tiered pricing — blank/zero falls back to unit_price.
    discount_price = db.Column(db.Float)
    wholesale_price = db.Column(db.Float)
    staff_price = db.Column(db.Float)
    student_price = db.Column(db.Float)
    parent_price = db.Column(db.Float)
    # Stock levels beyond the reorder threshold.
    opening_stock = db.Column(db.Integer, default=0)
    max_stock = db.Column(db.Integer)
    reorder_qty = db.Column(db.Integer)
    # Packaging / tax / logistics.
    unit = db.Column(db.String(20))                    # unit of measurement
    pack_size = db.Column(db.String(30))
    taxable = db.Column(db.Boolean, default=False)
    vat_rate = db.Column(db.Float)                     # percent
    preferred_supplier = db.Column(db.String(120))
    storage_location = db.Column(db.String(80))
    expiry_date = db.Column(db.Date)
    warranty_period = db.Column(db.String(40))

    branch = db.relationship('Branch')

    @property
    def low_stock(self):
        return self.stock_qty <= (self.reorder_level or 0)

    @property
    def out_of_stock(self):
        return (self.stock_qty or 0) <= 0

    @property
    def stock_value(self):
        """Cost value of the stock on hand — for inventory valuation."""
        return round((self.stock_qty or 0) * (self.cost_price or 0), 2)

    @property
    def margin_pct(self):
        if not self.unit_price:
            return None
        return round((self.unit_price - (self.cost_price or 0)) / self.unit_price * 100, 1)

    def price_for(self, buyer_type=None):
        """Selling price for a buyer type, honouring the tiered prices when set;
        otherwise the standard unit price."""
        tier = {'student': self.student_price, 'staff': self.staff_price,
                'parent': self.parent_price, 'wholesale': self.wholesale_price
                }.get((buyer_type or '').lower())
        return tier if (tier and tier > 0) else (self.unit_price or 0)

    def __repr__(self):
        return f'<Product {self.name} x{self.stock_qty}>'


class Sale(db.Model):
    __tablename__ = 'sales'

    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    receipt_no = db.Column(db.String(20))
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))   # optional buyer
    customer_name = db.Column(db.String(120))
    customer_type = db.Column(db.String(20))   # Student/Staff/Parent/Visitor/Walk-in
    payment_method = db.Column(db.String(20), default='Cash')
    subtotal = db.Column(db.Float, default=0)          # before discount
    discount = db.Column(db.Float, default=0)          # discount applied
    discount_code = db.Column(db.String(30))           # promo code used, if any
    total = db.Column(db.Float, default=0)             # payable after discount
    amount_paid = db.Column(db.Float, default=0)
    sold_by = db.Column(db.String(100))
    notes = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=local_now)

    student = db.relationship('Student')
    branch = db.relationship('Branch')
    items = db.relationship('SaleItem', backref='sale', lazy='dynamic',
                            cascade='all, delete-orphan')

    @property
    def change(self):
        return round((self.amount_paid or 0) - (self.total or 0), 2)

    @property
    def buyer(self):
        return (self.student.full_name if self.student else None) or self.customer_name or 'Walk-in'

    def __repr__(self):
        return f'<Sale {self.receipt_no} {self.total}>'


class SaleItem(db.Model):
    __tablename__ = 'sale_items'

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('sales_products.id'))
    description = db.Column(db.String(150))   # snapshot of the product name
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Float, default=0)
    line_total = db.Column(db.Float, default=0)

    product = db.relationship('Product')

    def __repr__(self):
        return f'<SaleItem {self.description} x{self.quantity}>'


class StockMovement(db.Model):
    """An auditable record of a single stock change — the inventory ledger.

    Every increase/decrease (a sale, a goods receipt, a manual adjustment,
    classroom use, damage, a transfer, a physical count correction…) writes one
    row, capturing the reason and the resulting quantity so stock is always
    reconcilable and the movement history is complete."""
    __tablename__ = 'stock_movements'

    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('sales_products.id'), nullable=False, index=True)
    direction = db.Column(db.String(3), nullable=False)      # 'in' | 'out'
    reason = db.Column(db.String(40), nullable=False)
    quantity = db.Column(db.Integer, default=0)              # always positive
    qty_after = db.Column(db.Integer)                        # stock level after this move
    unit_cost = db.Column(db.Float)                          # for stock-in valuation
    reference = db.Column(db.String(60))                    # invoice / PO / receipt no
    note = db.Column(db.String(200))
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'))   # set for sale movements
    performed_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now, index=True)

    product = db.relationship('Product')
    branch = db.relationship('Branch')

    @property
    def signed_qty(self):
        return (self.quantity or 0) * (1 if self.direction == 'in' else -1)

    def __repr__(self):
        return f'<StockMovement {self.direction} {self.quantity} {self.reason}>'


PO_STATUSES = ['Draft', 'Pending Approval', 'Approved', 'Ordered',
               'Partially Received', 'Received', 'Cancelled']
PURCHASE_METHODS = ['Cash', 'Bank Transfer', 'POS', 'Credit']


class Supplier(db.Model):
    __tablename__ = 'suppliers'

    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    company_name = db.Column(db.String(150), nullable=False)
    contact_person = db.Column(db.String(100))
    phone = db.Column(db.String(30))
    email = db.Column(db.String(120))
    address = db.Column(db.String(200))
    tax_id = db.Column(db.String(40))
    bank_details = db.Column(db.String(200))
    products_supplied = db.Column(db.String(255))
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)

    branch = db.relationship('Branch')

    def __repr__(self):
        return f'<Supplier {self.company_name}>'


class PurchaseOrder(db.Model):
    __tablename__ = 'purchase_orders'

    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    po_number = db.Column(db.String(20))
    status = db.Column(db.String(20), default='Draft')
    expected_date = db.Column(db.Date)
    invoice_number = db.Column(db.String(40))
    notes = db.Column(db.Text)
    total = db.Column(db.Float, default=0)
    created_by = db.Column(db.String(100))
    approved_by = db.Column(db.String(100))
    approved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=local_now)

    supplier = db.relationship('Supplier')
    branch = db.relationship('Branch')
    items = db.relationship('PurchaseOrderItem', backref='po', lazy='dynamic',
                            cascade='all, delete-orphan')

    @property
    def received_value(self):
        return round(sum(i.received_value for i in self.items), 2)

    @property
    def is_open(self):
        return self.status not in ('Received', 'Cancelled')

    def __repr__(self):
        return f'<PurchaseOrder {self.po_number} {self.status}>'


class PurchaseOrderItem(db.Model):
    __tablename__ = 'purchase_order_items'

    id = db.Column(db.Integer, primary_key=True)
    po_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('sales_products.id'))
    description = db.Column(db.String(150))
    quantity = db.Column(db.Integer, default=0)
    unit_cost = db.Column(db.Float, default=0)
    quantity_received = db.Column(db.Integer, default=0)

    product = db.relationship('Product')

    @property
    def line_total(self):
        return round((self.quantity or 0) * (self.unit_cost or 0), 2)

    @property
    def received_value(self):
        return round((self.quantity_received or 0) * (self.unit_cost or 0), 2)

    @property
    def outstanding_qty(self):
        return max((self.quantity or 0) - (self.quantity_received or 0), 0)


class SupplierPayment(db.Model):
    __tablename__ = 'supplier_payments'

    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    po_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'))
    amount = db.Column(db.Float, default=0)
    method = db.Column(db.String(20), default='Cash')
    reference = db.Column(db.String(60))
    note = db.Column(db.String(200))
    paid_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)

    supplier = db.relationship('Supplier')

    def __repr__(self):
        return f'<SupplierPayment {self.supplier_id} {self.amount}>'


STOCK_AUDIT_STATUSES = ['Counting', 'Completed', 'Cancelled']


class StockAudit(db.Model):
    """A physical stock-count session: snapshot the system quantities for a set
    of products, enter the counted quantities, review the variances, then sign
    off — applying the corrections to stock (ledgered) and posting the net
    shrinkage/gain to the finance ledger. One row per count exercise."""
    __tablename__ = 'stock_audits'

    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    reference = db.Column(db.String(20))
    scope_category = db.Column(db.String(40))       # count filtered to a category (optional)
    scope_location = db.Column(db.String(80))       # …or a storage location (optional)
    status = db.Column(db.String(15), default='Counting')
    note = db.Column(db.String(200))
    started_by = db.Column(db.String(100))
    approved_by = db.Column(db.String(100))
    variance_value = db.Column(db.Float, default=0)   # signed net cost value applied
    ledger_posted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=local_now)
    completed_at = db.Column(db.DateTime)

    branch = db.relationship('Branch')
    items = db.relationship('StockAuditItem', backref='audit', lazy='dynamic',
                            cascade='all, delete-orphan')

    @property
    def counted_list(self):
        return [i for i in self.items if i.counted_qty is not None]

    @property
    def is_open(self):
        return self.status == 'Counting'

    def __repr__(self):
        return f'<StockAudit {self.reference} {self.status}>'


class StockAuditItem(db.Model):
    __tablename__ = 'stock_audit_items'

    id = db.Column(db.Integer, primary_key=True)
    audit_id = db.Column(db.Integer, db.ForeignKey('stock_audits.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('sales_products.id'))
    product_name = db.Column(db.String(150))          # snapshot of the name
    system_qty = db.Column(db.Integer, default=0)     # on-hand when the sheet was built
    counted_qty = db.Column(db.Integer)               # None until physically counted
    unit_cost = db.Column(db.Float, default=0)        # snapshot, for variance valuation
    note = db.Column(db.String(200))

    product = db.relationship('Product')

    @property
    def counted(self):
        return self.counted_qty is not None

    @property
    def variance_qty(self):
        if self.counted_qty is None:
            return None
        return self.counted_qty - (self.system_qty or 0)

    @property
    def variance_value(self):
        v = self.variance_qty
        return round((v or 0) * (self.unit_cost or 0), 2) if v is not None else 0.0

    def __repr__(self):
        return f'<StockAuditItem {self.product_name} {self.counted_qty}/{self.system_qty}>'


FIXED_ASSET_CATEGORIES = ['ICT Equipment', 'Furniture & Fittings', 'Laboratory Equipment',
                          'Vehicles', 'Machinery', 'Buildings', 'Sports Equipment',
                          'Kitchen Equipment', 'Musical Instruments', 'Books & Library',
                          'Other']
FIXED_ASSET_STATUSES = ['In Use', 'In Store', 'Under Repair', 'Disposed', 'Lost']


class FixedAsset(db.Model):
    """A capital item the school owns and tracks over its life — lab equipment,
    ICT gear, furniture, vehicles. Either registered directly or converted from
    an inventory product (which draws the units out of stock). Carries a
    straight-line depreciation schedule so the register shows current book
    value, and records disposal (with proceeds posted to the finance ledger)."""
    __tablename__ = 'fixed_assets'

    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    name = db.Column(db.String(150), nullable=False)
    asset_tag = db.Column(db.String(40), index=True)
    category = db.Column(db.String(40), default='Other')
    description = db.Column(db.Text)
    serial_number = db.Column(db.String(80))
    acquisition_cost = db.Column(db.Float, default=0)
    acquisition_date = db.Column(db.Date)
    supplier = db.Column(db.String(120))
    location = db.Column(db.String(80))
    custodian = db.Column(db.String(120))
    status = db.Column(db.String(20), default='In Use')
    # Straight-line depreciation inputs (life in years, residual value).
    useful_life_years = db.Column(db.Integer)
    salvage_value = db.Column(db.Float, default=0)
    # Provenance + disposal.
    source_product_id = db.Column(db.Integer, db.ForeignKey('sales_products.id'))
    quantity = db.Column(db.Integer, default=1)
    disposed_on = db.Column(db.Date)
    disposal_amount = db.Column(db.Float)
    disposal_note = db.Column(db.String(200))
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)

    branch = db.relationship('Branch')
    source_product = db.relationship('Product')

    @property
    def is_disposed(self):
        return self.status == 'Disposed'

    @property
    def age_years(self):
        if not self.acquisition_date:
            return 0.0
        end = self.disposed_on or local_now().date()
        return max((end - self.acquisition_date).days / 365.25, 0.0)

    @property
    def annual_depreciation(self):
        life = self.useful_life_years or 0
        if life <= 0:
            return 0.0
        base = (self.acquisition_cost or 0) - (self.salvage_value or 0)
        return round(max(base, 0) / life, 2)

    @property
    def accumulated_depreciation(self):
        base = (self.acquisition_cost or 0) - (self.salvage_value or 0)
        if base <= 0 or not self.annual_depreciation:
            return 0.0
        return round(min(self.annual_depreciation * self.age_years, base), 2)

    @property
    def book_value(self):
        """Current carrying value: cost − accumulated depreciation (0 once
        disposed)."""
        if self.is_disposed:
            return 0.0
        return round((self.acquisition_cost or 0) - self.accumulated_depreciation, 2)

    def __repr__(self):
        return f'<FixedAsset {self.asset_tag or self.name}>'


class PromoCode(db.Model):
    """A discount voucher applied at checkout — percentage or fixed amount, with
    optional minimum spend, expiry, usage cap and a category restriction."""
    __tablename__ = 'promo_codes'

    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    code = db.Column(db.String(30), nullable=False, index=True)
    description = db.Column(db.String(120))
    kind = db.Column(db.String(10), default='percent')     # 'percent' | 'fixed'
    value = db.Column(db.Float, default=0)                  # 10 (=10%) or 500 (=₦500)
    min_purchase = db.Column(db.Float, default=0)
    category = db.Column(db.String(40))                     # limit to one category (optional)
    expires_on = db.Column(db.Date)
    usage_limit = db.Column(db.Integer)                    # None = unlimited
    used_count = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)

    branch = db.relationship('Branch')

    def discount_for(self, subtotal):
        """The discount this code yields on a subtotal, capped at the subtotal."""
        if self.kind == 'percent':
            d = (subtotal or 0) * (self.value or 0) / 100.0
        else:
            d = self.value or 0
        return round(min(max(d, 0), subtotal or 0), 2)

    def usable(self, subtotal, today):
        """(ok, reason) — whether the code may be applied to this subtotal now."""
        if not self.is_active:
            return False, 'This code is inactive.'
        if self.expires_on and self.expires_on < today:
            return False, 'This code has expired.'
        if self.usage_limit is not None and (self.used_count or 0) >= self.usage_limit:
            return False, 'This code has reached its usage limit.'
        if (self.min_purchase or 0) > (subtotal or 0):
            return False, f'Spend at least {self.min_purchase:g} to use this code.'
        return True, ''

    def __repr__(self):
        return f'<PromoCode {self.code}>'
