"""WAEC / NECO exam timetables (Tools → WAEC / NECO Timetable).

A school copies the official SSCE timetable into its own version — every paper
with its date and time — then adds the hall and invigilators, checks which of
its candidates sit each paper and spots clashes, and prints it for the notice
board or as a personal timetable for each candidate."""
from models.models import db, local_now


class ExamTimetable(db.Model):
    __tablename__ = 'exam_timetables'

    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    board = db.Column(db.String(10), nullable=False, default='waec')   # 'waec' | 'neco'
    title = db.Column(db.String(150), nullable=False)
    year = db.Column(db.Integer)
    start_date = db.Column(db.Date)            # the exam window — paper dates must fall inside it
    end_date = db.Column(db.Date)
    notes = db.Column(db.Text)                                        # shown under the title on exports
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

    papers = db.relationship('ExamTimetablePaper', backref='timetable', cascade='all, delete-orphan',
                             order_by='(ExamTimetablePaper.exam_date, ExamTimetablePaper.start_time, '
                                      'ExamTimetablePaper.id)')

    @property
    def board_label(self):
        return 'NECO' if self.board == 'neco' else 'WAEC'


class ExamTimetablePaper(db.Model):
    __tablename__ = 'exam_timetable_papers'

    id = db.Column(db.Integer, primary_key=True)
    timetable_id = db.Column(db.Integer, db.ForeignKey('exam_timetables.id', ondelete='CASCADE'),
                             nullable=False, index=True)
    exam_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    subject = db.Column(db.String(120), nullable=False)
    paper = db.Column(db.String(120))          # e.g. "Paper 2 (Essay)"
    kind = db.Column(db.String(20))            # objective | essay | practical | oral | other
    venue = db.Column(db.String(120))
    invigilators = db.Column(db.String(255))
    notes = db.Column(db.String(255))
