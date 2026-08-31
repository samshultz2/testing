"""Branches (multi-branch support).

A school may run several branches that share one structure. Branch-owned records
carry a ``branch_id``; *central* users (Director of Studies, Exams & Standards,
IT) see across all branches, while *branch* users are scoped to their own.

Stage 1 only introduces the model + columns and backfills existing data to a
default branch — no query filtering happens yet (that is Stage 2).
"""
from models.models import db, local_now


class Branch(db.Model):
    __tablename__ = 'branches'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    code = db.Column(db.String(20), unique=True)        # short tag, e.g. JEM
    address = db.Column(db.String(200))
    phone = db.Column(db.String(30))
    is_default = db.Column(db.Boolean, default=False)   # the fallback branch
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)

    @staticmethod
    def get_default():
        """The default branch, or the first one if none is flagged default."""
        return (Branch.query.filter_by(is_default=True).first()
                or Branch.query.order_by(Branch.id).first())

    def __repr__(self):
        return f'<Branch {self.name}>'
