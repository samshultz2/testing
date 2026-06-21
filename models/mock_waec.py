"""
Mock WAEC Examination Models

Schools run several internal "Mock WAEC" sittings per academic session to
rehearse the real WASSCE. Unlike real WAEC (which stores only letter grades),
mocks are marked out of 100 per subject and the A1-F9 grade is derived from the
score — this gives finer-grained trends across sittings.

Mirrors the Mock JAMB event model: an exam *event* (MockWAECExam, multiple per
session, branch-scoped) owns many per-subject *results* (MockWAECResult).
"""
from datetime import datetime
from models.models import db

# Standard WASSCE grade boundaries (score out of 100 -> grade).
PASS_GRADES = {'A1', 'B2', 'B3', 'C4', 'C5', 'C6'}        # credit or better
DISTINCTION_GRADES = {'A1', 'B2', 'B3'}
GRADE_POINTS = {'A1': 1, 'B2': 2, 'B3': 3, 'C4': 4, 'C5': 5,
                'C6': 6, 'D7': 7, 'E8': 8, 'F9': 9}


def waec_grade_from_score(score):
    """Map a 0-100 score to its WASSCE grade. Returns None for a missing score."""
    if score is None:
        return None
    s = max(0, min(100, int(round(score))))
    if s >= 75:
        return 'A1'
    if s >= 70:
        return 'B2'
    if s >= 65:
        return 'B3'
    if s >= 60:
        return 'C4'
    if s >= 55:
        return 'C5'
    if s >= 50:
        return 'C6'
    if s >= 45:
        return 'D7'
    if s >= 40:
        return 'E8'
    return 'F9'


class MockWAECExam(db.Model):
    """A single Mock WAEC examination event (e.g. 'First Mock WAEC 2025/2026')."""
    __tablename__ = 'mock_waec_exams'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    exam_number = db.Column(db.Integer, nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('academic_sessions.id'), nullable=False)
    exam_date = db.Column(db.Date, nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))   # owning branch (scoping)
    is_active = db.Column(db.Boolean, default=True)
    is_completed = db.Column(db.Boolean, default=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    session = db.relationship('AcademicSession', backref=db.backref('mock_waec_exams', lazy='dynamic'))
    branch = db.relationship('Branch')
    results = db.relationship('MockWAECResult', backref='exam', lazy='dynamic',
                              cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('session_id', 'exam_number', 'branch_id',
                            name='unique_mock_waec_exam_per_session'),
    )

    @property
    def display_name(self):
        ordinals = {1: 'First', 2: 'Second', 3: 'Third', 4: 'Fourth'}
        return f"{ordinals.get(self.exam_number, f'{self.exam_number}th')} Mock WAEC"

    @property
    def student_count(self):
        """Distinct students with at least one subject result in this exam."""
        return (db.session.query(MockWAECResult.student_id)
                .filter_by(mock_exam_id=self.id).distinct().count())


class MockWAECResult(db.Model):
    """One subject result for a student in a Mock WAEC exam (score + derived grade)."""
    __tablename__ = 'mock_waec_results'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    mock_exam_id = db.Column(db.Integer, db.ForeignKey('mock_waec_exams.id'), nullable=False)
    subject = db.Column(db.String(50), nullable=False)
    score = db.Column(db.Integer)            # 0-100
    grade = db.Column(db.String(2))          # A1-F9, derived from score
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    student = db.relationship('Student', backref=db.backref('mock_waec_results', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('student_id', 'mock_exam_id', 'subject',
                            name='unique_student_mock_waec_subject'),
    )

    def apply_score(self, score, grade=None):
        """Set the score and (auto-)derive the grade unless one is supplied."""
        self.score = score
        self.grade = grade or waec_grade_from_score(score)

    @property
    def is_pass(self):
        return self.grade in PASS_GRADES

    @property
    def is_distinction(self):
        return self.grade in DISTINCTION_GRADES


class MockWAECAnalytics:
    """Analytics and insights for Mock WAEC examinations."""

    @staticmethod
    def _summarise(results):
        """Aggregate a list of MockWAECResult rows into credit/quality metrics."""
        grades = [r.grade for r in results if r.grade]
        scores = [r.score for r in results if r.score is not None]
        credits = sum(1 for g in grades if g in PASS_GRADES)
        distinctions = sum(1 for g in grades if g in DISTINCTION_GRADES)
        fails = sum(1 for g in grades if g in ('E8', 'F9'))
        return {
            'subjects': len(results),
            'credits': credits,
            'distinctions': distinctions,
            'fails': fails,
            'average_score': round(sum(scores) / len(scores), 1) if scores else None,
            'has_5_credits': credits >= 5,
        }

    @staticmethod
    def get_student_exam_summary(student_id, exam_id):
        results = MockWAECResult.query.filter_by(
            student_id=student_id, mock_exam_id=exam_id).all()
        if not results:
            return None
        summary = MockWAECAnalytics._summarise(results)
        summary['results'] = sorted(results, key=lambda r: r.subject)
        return summary

    @staticmethod
    def get_student_progress(student_id, session_id=None):
        """Credit/score trajectory across the student's Mock WAEC sittings."""
        q = (MockWAECResult.query.filter_by(student_id=student_id).join(MockWAECExam))
        if session_id:
            q = q.filter(MockWAECExam.session_id == session_id)
        rows = q.order_by(MockWAECExam.exam_number).all()
        if not rows:
            return None

        by_exam = {}
        for r in rows:
            by_exam.setdefault(r.mock_exam_id, []).append(r)

        progress = []
        for exam_id, results in sorted(
                by_exam.items(), key=lambda kv: kv[1][0].exam.exam_number):
            exam = results[0].exam
            s = MockWAECAnalytics._summarise(results)
            progress.append({
                'exam': exam.display_name,
                'exam_number': exam.exam_number,
                'exam_date': exam.exam_date,
                'credits': s['credits'],
                'distinctions': s['distinctions'],
                'average_score': s['average_score'],
                'has_5_credits': s['has_5_credits'],
            })

        if len(progress) >= 2:
            credit_change = progress[-1]['credits'] - progress[0]['credits']
            trend = ('improving' if credit_change > 0
                     else 'declining' if credit_change < 0 else 'stable')
        else:
            credit_change = 0
            trend = 'insufficient_data'

        return {
            'student_id': student_id,
            'progress': progress,
            'exam_count': len(progress),
            'credit_change': credit_change,
            'trend': trend,
            'latest_credits': progress[-1]['credits'],
            'best_credits': max(p['credits'] for p in progress),
        }

    @staticmethod
    def get_exam_statistics(exam_id):
        exam = db.session.get(MockWAECExam, exam_id)
        if not exam:
            return None
        results = exam.results.all()
        if not results:
            return {'exam': exam, 'student_count': 0, 'statistics': None}

        # Per-student credit summaries.
        by_student = {}
        for r in results:
            by_student.setdefault(r.student_id, []).append(r)
        summaries = [MockWAECAnalytics._summarise(rs) for rs in by_student.values()]
        with_5 = sum(1 for s in summaries if s['has_5_credits'])

        # Per-subject performance.
        by_subject = {}
        for r in results:
            by_subject.setdefault(r.subject, []).append(r)
        subject_analysis = []
        for subject, rs in by_subject.items():
            scores = [r.score for r in rs if r.score is not None]
            passes = sum(1 for r in rs if r.grade in PASS_GRADES)
            subject_analysis.append({
                'subject': subject,
                'count': len(rs),
                'average': round(sum(scores) / len(scores), 1) if scores else 0,
                'pass_rate': round(passes / len(rs) * 100, 1) if rs else 0,
            })

        # Overall grade distribution.
        dist = {g: 0 for g in GRADE_POINTS}
        for r in results:
            if r.grade in dist:
                dist[r.grade] += 1

        return {
            'exam': exam,
            'student_count': len(by_student),
            'statistics': {
                'with_5_credits': with_5,
                'with_5_credits_pct': round(with_5 / len(summaries) * 100, 1) if summaries else 0,
                'avg_credits': round(sum(s['credits'] for s in summaries) / len(summaries), 1) if summaries else 0,
            },
            'grade_distribution': dist,
            'subject_analysis': sorted(subject_analysis, key=lambda x: x['average'], reverse=True),
            'top_performers': sorted(
                by_student.items(),
                key=lambda kv: (MockWAECAnalytics._summarise(kv[1])['credits'],
                                MockWAECAnalytics._summarise(kv[1])['average_score'] or 0),
                reverse=True)[:10],
        }

    @staticmethod
    def compare_mock_exams(session_id, branch_id=None):
        q = MockWAECExam.query.filter_by(session_id=session_id)
        if branch_id is not None:
            q = q.filter(MockWAECExam.branch_id == branch_id)
        comparison = []
        for exam in q.order_by(MockWAECExam.exam_number).all():
            stats = MockWAECAnalytics.get_exam_statistics(exam.id)
            if stats and stats.get('student_count'):
                comparison.append({
                    'exam': exam,
                    'exam_number': exam.exam_number,
                    'student_count': stats['student_count'],
                    'avg_credits': stats['statistics']['avg_credits'],
                    'with_5_credits_pct': stats['statistics']['with_5_credits_pct'],
                })
        return comparison

    @staticmethod
    def predict_waec(student_id, session_id=None):
        """Predict real-WAEC outcome (expected credits + quality) from the mock
        trajectory. Weights recent sittings more heavily."""
        progress = MockWAECAnalytics.get_student_progress(student_id, session_id)
        if not progress:
            return None

        weighted = [(i + 1, p['credits']) for i, p in enumerate(progress['progress'])]
        total_w = sum(w for w, _ in weighted)
        predicted_credits = round(sum(w * c for w, c in weighted) / total_w)
        if progress['trend'] == 'improving':
            predicted_credits = min(9, predicted_credits + 1)
        elif progress['trend'] == 'declining':
            predicted_credits = max(0, predicted_credits - 1)

        quality = ('EXCELLENT' if predicted_credits >= 8
                   else 'GOOD' if predicted_credits >= 6
                   else 'AVERAGE' if predicted_credits >= 5 else 'POOR')
        exam_count = progress['exam_count']
        confidence = min(90, 55 + exam_count * 10)
        return {
            'predicted_credits': predicted_credits,
            'meets_minimum': predicted_credits >= 5,
            'quality': quality,
            'confidence': confidence,
            'trend': progress['trend'],
            'based_on_exams': exam_count,
        }
