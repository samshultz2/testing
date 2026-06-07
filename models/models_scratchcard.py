"""Result-checker scratch cards (Nigerian-style PIN cards).

A card carries a serial + PIN and a limited number of result checks. A
student/parent enters their Student ID + the card PIN on the public portal to
view that term's result. Each successful check consumes one use.
"""
import secrets
import string

from models.models import db, local_now


def _gen_token(length, alphabet):
    return ''.join(secrets.choice(alphabet) for _ in range(length))


class ScratchCard(db.Model):
    __tablename__ = 'scratch_cards'

    id = db.Column(db.Integer, primary_key=True)
    serial = db.Column(db.String(20), unique=True, nullable=False)
    pin = db.Column(db.String(20), unique=True, nullable=False)
    max_uses = db.Column(db.Integer, default=5)
    used_count = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    # Optional: restrict a card to one term and/or one student.
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'))
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))
    batch_label = db.Column(db.String(60))
    created_at = db.Column(db.DateTime, default=local_now)

    term = db.relationship('Term')
    student = db.relationship('Student')
    checks = db.relationship('ResultCheckLog', backref='card',
                             cascade='all, delete-orphan', lazy='dynamic')

    @property
    def uses_left(self):
        return max((self.max_uses or 0) - (self.used_count or 0), 0)

    def can_use(self):
        return self.is_active and self.uses_left > 0

    @staticmethod
    def generate_unique(max_uses=5, term_id=None, student_id=None, batch_label=None):
        """Build (not commit) a card with unique serial + PIN."""
        digits = string.digits
        alnum = string.ascii_uppercase + string.digits
        while True:
            serial = 'SC' + _gen_token(8, digits)
            if not ScratchCard.query.filter_by(serial=serial).first():
                break
        while True:
            pin = _gen_token(12, alnum)
            if not ScratchCard.query.filter_by(pin=pin).first():
                break
        return ScratchCard(serial=serial, pin=pin, max_uses=max_uses,
                           term_id=term_id, student_id=student_id,
                           batch_label=batch_label)

    def __repr__(self):
        return f'<ScratchCard {self.serial} {self.used_count}/{self.max_uses}>'


class ResultCheckLog(db.Model):
    """Audit trail of every result-checker access (for investigations)."""
    __tablename__ = 'result_check_logs'

    id = db.Column(db.Integer, primary_key=True)
    card_id = db.Column(db.Integer, db.ForeignKey('scratch_cards.id'))
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'))
    success = db.Column(db.Boolean, default=True)
    detail = db.Column(db.String(200))
    ip_address = db.Column(db.String(60))
    user_agent = db.Column(db.String(300))
    checked_at = db.Column(db.DateTime, default=local_now)

    student = db.relationship('Student')
    term = db.relationship('Term')

    def __repr__(self):
        return f'<ResultCheckLog student{self.student_id} {"ok" if self.success else "fail"}>'
