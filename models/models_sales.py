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
    total = db.Column(db.Float, default=0)
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
