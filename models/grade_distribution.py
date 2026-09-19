"""A branch's own subject-wise grade/score-band distribution.

Some branches don't enter individual student WAEC/JAMB results into this
system at all — instead they send head office a whole-class summary sheet
per subject (candidates sat + a count per grade/score-band), already
tallied on their end. This model captures that summary (via OCR photo,
paste, or file upload — never the source document itself) so it can be
merged into the Subject-Wise Grade Breakdown report alongside branches
that DO have per-student rows in WAECResult/JAMBResult/mock tables.

The merge is per (branch, subject): a stored distribution here always wins
over whatever the DB rows would compute for that same branch/subject, since
it's the branch's own authoritative figure — see
routes.results.analytics._load_grade_breakdown.
"""
import json

from models.models import db, local_now


class BranchGradeDistribution(db.Model):
    __tablename__ = 'branch_grade_distributions'

    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=False, index=True)
    exam = db.Column(db.String(12), nullable=False)                 # waec|jamb|mock_waec|mock_jamb
    exam_year = db.Column(db.Integer)                                # waec/jamb period
    mock_session_id = db.Column(db.Integer, db.ForeignKey('academic_sessions.id'))  # mock_* period
    mock_exam_number = db.Column(db.Integer)                         # mock_* period
    subject = db.Column(db.String(60), nullable=False)
    candidates = db.Column(db.Integer, nullable=False, default=0)    # "No. Sat"
    band_counts = db.Column(db.Text, nullable=False, default='{}')   # JSON {band: count}
    source = db.Column(db.String(10))                                # ocr|paste|file|manual
    imported_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

    branch = db.relationship('Branch')

    def counts(self):
        try:
            return {k: int(v) for k, v in json.loads(self.band_counts or '{}').items()}
        except (TypeError, ValueError):
            return {}

    def set_counts(self, d):
        self.band_counts = json.dumps({k: int(v) for k, v in (d or {}).items()})
