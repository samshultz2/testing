"""Sales & Inventory (Stage 5).

Bursars sell items (textbooks, workbooks, notebooks, uniforms…) and track stock.
Everything is branch-scoped: each branch has its own products and sales.
"""
from models.models import db, local_now

PRODUCT_CATEGORIES = ['Textbook', 'Workbook', 'Notebook', 'Uniform',
                      'Stationery', 'Other']
SALE_METHODS = ['Cash', 'Transfer', 'POS']


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
    reorder_level = db.Column(db.Integer, default=0)   # low-stock threshold
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)

    branch = db.relationship('Branch')

    @property
    def low_stock(self):
        return self.stock_qty <= (self.reorder_level or 0)

    def __repr__(self):
        return f'<Product {self.name} x{self.stock_qty}>'


class Sale(db.Model):
    __tablename__ = 'sales'

    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    receipt_no = db.Column(db.String(20))
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))   # optional buyer
    customer_name = db.Column(db.String(120))
    payment_method = db.Column(db.String(20), default='Cash')
    total = db.Column(db.Float, default=0)
    amount_paid = db.Column(db.Float, default=0)
    sold_by = db.Column(db.String(100))
    notes = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=local_now)

    student = db.relationship('Student')
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
