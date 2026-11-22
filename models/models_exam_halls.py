"""Saved exam-hall allocations (Tools → Exam Hall Allocator).

A plan is a frozen snapshot of one generated arrangement — which candidate sits
in which hall and seat — so it can be reopened, printed and exported later
exactly as it was, even after students move class or leave."""
import json

from models.models import db, local_now


class ExamHallPlan(db.Model):
    __tablename__ = 'exam_hall_plans'

    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'))
    name = db.Column(db.String(150), nullable=False)
    # The form inputs that produced it (classes, halls, options, seed).
    params = db.Column(db.Text)
    # The arrangement itself: halls → seats → candidates, plus summary stats.
    snapshot = db.Column(db.Text, nullable=False)
    total_students = db.Column(db.Integer, default=0)
    hall_count = db.Column(db.Integer, default=0)
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

    term = db.relationship('Term')

    @property
    def result(self):
        try:
            return json.loads(self.snapshot or '{}')
        except ValueError:
            return {}

    @property
    def payload(self):
        try:
            return json.loads(self.params or '{}')
        except ValueError:
            return {}
