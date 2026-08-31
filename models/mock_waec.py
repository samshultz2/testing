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

# Admission to a Nigerian tertiary institution needs 5 credits *including* these
# two — 5 credits alone (e.g. failing English) does not qualify a student.
CORE_SUBJECTS = ('English Language', 'Mathematics')


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


def _stddev(values):
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    import math
    return round(math.sqrt(sum((x - mean) ** 2 for x in values) / len(values)), 1)


def _quartiles(values):
    """Q1 / median / Q3 (linear interpolation), plus min/max/mean."""
    if not values:
        return {'q1': 0, 'median': 0, 'q3': 0, 'min': 0, 'max': 0, 'mean': 0}
    import math
    s = sorted(values)

    def pct(p):
        k = (len(s) - 1) * p / 100
        f, c = math.floor(k), math.ceil(k)
        return s[int(k)] if f == c else s[f] * (c - k) + s[c] * (k - f)
    return {'q1': round(pct(25), 1), 'median': round(pct(50), 1), 'q3': round(pct(75), 1),
            'min': min(s), 'max': max(s), 'mean': round(sum(s) / len(s), 1)}


def _score_stats(values):
    q = _quartiles(values)
    q['n'] = len(values)
    q['std_dev'] = _stddev(values)
    return q


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
        # Which of English/Maths are credited — 5 credits without these don't admit.
        credited = {r.subject for r in results if r.grade in PASS_GRADES}
        missing_core = [s for s in CORE_SUBJECTS if s not in credited]
        return {
            'subjects': len(results),
            'credits': credits,
            'distinctions': distinctions,
            'fails': fails,
            'average_score': round(sum(scores) / len(scores), 1) if scores else None,
            'has_5_credits': credits >= 5,
            'has_core': not missing_core,
            'missing_core': missing_core,
            # The admission-grade flag: 5 credits *and* both English and Maths.
            'has_5_incl_core': credits >= 5 and not missing_core,
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
        return MockWAECAnalytics._progress_from_rows(student_id, rows)

    @staticmethod
    def _progress_from_rows(student_id, rows):
        """Build the progress dict from already-loaded rows (each with ``.exam``).
        Lets a cohort be computed from one batched query."""
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
                'has_5_incl_core': s['has_5_incl_core'],
                'missing_core': s['missing_core'],
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
            'latest_has_5_incl_core': progress[-1]['has_5_incl_core'],
            'latest_missing_core': progress[-1]['missing_core'],
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
        with_5_core = sum(1 for s in summaries if s['has_5_incl_core'])

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
                # The honest admission metric: 5 credits including English & Maths.
                'with_5_incl_core': with_5_core,
                'with_5_incl_core_pct': round(with_5_core / len(summaries) * 100, 1) if summaries else 0,
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
    def _ordered_subjects(present):
        """Subjects in canonical WAEC order (core first), extras appended A-Z."""
        try:
            from utils.helpers import WAEC_SUBJECTS
            order = {name: i for i, name in enumerate(WAEC_SUBJECTS)}
        except Exception:
            order = {}
        return sorted(present, key=lambda s: (order.get(s, len(order)), s))

    @staticmethod
    def get_broadsheet(exam_id):
        """The full score+grade matrix for an exam plus the per-subject summary
        block (offered / passed / failed / average score / average grade / grade
        spread) that schools record under their hand-written broadsheets.

        Returns ``None`` when the exam is missing. ``rows`` is empty (but the
        shape is still valid) when no results have been entered yet.
        """
        exam = db.session.get(MockWAECExam, exam_id)
        if not exam:
            return None

        from models.models import Student
        results = (MockWAECResult.query.filter_by(mock_exam_id=exam_id)
                   .join(Student).all())
        grade_order = list(GRADE_POINTS)          # A1..F9 in order

        cells, students, present = {}, {}, set()
        for r in results:
            present.add(r.subject)
            cells.setdefault(r.student_id, {})[r.subject] = r
            students[r.student_id] = r.student
        subjects = MockWAECAnalytics._ordered_subjects(present)

        # One row per student (admission-register order: surname, first name).
        rows = []
        for sid, student in students.items():
            srs = list(cells[sid].values())
            summary = MockWAECAnalytics._summarise(srs)
            rows.append({
                'student': student,
                'cells': cells[sid],                       # {subject: MockWAECResult}
                'credits': summary['credits'],
                'distinctions': summary['distinctions'],
                'average_score': summary['average_score'],
                'has_5_incl_core': summary['has_5_incl_core'],
                'total_score': sum(r.score for r in srs if r.score is not None),
            })
        rows.sort(key=lambda x: ((x['student'].surname or '').lower(),
                                 (x['student'].first_name or '').lower()))

        # Per-subject summary column (matches the foot of a paper broadsheet).
        subject_summary = {}
        for subj in subjects:
            srs = [cells[sid][subj] for sid in cells if subj in cells[sid]]
            scores = [r.score for r in srs if r.score is not None]
            offered = len(srs)
            passed = sum(1 for r in srs if r.grade in PASS_GRADES)
            avg = round(sum(scores) / len(scores), 1) if scores else None
            dist = {g: 0 for g in grade_order}
            for r in srs:
                if r.grade in dist:
                    dist[r.grade] += 1
            subject_summary[subj] = {
                'offered': offered,
                'passed': passed,
                'failed': offered - passed,
                'avg_score': avg,
                'avg_grade': waec_grade_from_score(avg) if avg is not None else '—',
                'pass_rate': round(passed / offered * 100, 1) if offered else 0,
                'distribution': dist,
            }

        # Whole-exam grade spread (counts + percentages), for the school summary.
        total_entries = len(results)
        overall_dist = {g: 0 for g in grade_order}
        for r in results:
            if r.grade in overall_dist:
                overall_dist[r.grade] += 1
        overall_pct = {g: (round(overall_dist[g] / total_entries * 100, 1)
                           if total_entries else 0) for g in grade_order}

        summaries = [MockWAECAnalytics._summarise(list(cells[sid].values())) for sid in cells]
        n = len(summaries)
        school = {
            'students': n,
            'subject_entries': total_entries,
            'with_5_credits': sum(1 for s in summaries if s['has_5_credits']),
            'with_5_incl_core': sum(1 for s in summaries if s['has_5_incl_core']),
            'with_5_incl_core_pct': round(
                sum(1 for s in summaries if s['has_5_incl_core']) / n * 100, 1) if n else 0,
            'avg_credits': round(sum(s['credits'] for s in summaries) / n, 1) if n else 0,
        }

        return {
            'exam': exam,
            'subjects': subjects,
            'rows': rows,
            'subject_summary': subject_summary,
            'grade_order': grade_order,
            'grade_distribution': overall_dist,
            'grade_distribution_pct': overall_pct,
            'school': school,
        }

    @staticmethod
    def get_analytics(exam_id):
        """Deeper, derived insights on top of the broadsheet: subject-difficulty
        ranking, per-subject grade spread, the cohort credit histogram, and the
        core-subject (English/Maths) credit rates that decide admissions."""
        bs = MockWAECAnalytics.get_broadsheet(exam_id)
        if not bs or not bs['rows']:
            return bs and {'exam': bs['exam'], 'empty': True}

        ss = bs['subject_summary']
        subjects = bs['subjects']

        # Subject difficulty: hardest (lowest pass rate) first.
        difficulty = sorted(
            ({'subject': s, **ss[s]} for s in subjects),
            key=lambda d: (d['pass_rate'], d['avg_score'] if d['avg_score'] is not None else 0))

        # Credit histogram across students (0..9 credits).
        from collections import Counter
        credit_counts = Counter(r['credits'] for r in bs['rows'])
        n = len(bs['rows'])
        credit_histogram = [{
            'credits': k,
            'count': credit_counts.get(k, 0),
            'pct': round(credit_counts.get(k, 0) / n * 100, 1) if n else 0,
        } for k in range(0, 10)]

        # Core-subject credit rates (5 credits don't admit without English & Maths).
        def _credit_rate(subject):
            d = ss.get(subject)
            if not d or not d['offered']:
                return None
            return round(d['passed'] / d['offered'] * 100, 1)

        # Statistical depth (mirrors the real-WAEC analytics): spread of scores
        # overall, per student, and per subject — mean, std-dev and quartiles.
        all_scores, subject_scores = [], {s: [] for s in subjects}
        per_student_avg = []
        for row in bs['rows']:
            sv = []
            for s in subjects:
                r = row['cells'].get(s)
                if r and r.score is not None:
                    all_scores.append(r.score)
                    subject_scores[s].append(r.score)
                    sv.append(r.score)
            if sv:
                per_student_avg.append(round(sum(sv) / len(sv), 1))
        score_stats = {'overall': _score_stats(all_scores),
                       'per_student': _score_stats(per_student_avg)}
        subject_stats = {s: _score_stats(subject_scores[s]) for s in subjects}

        # Top & bottom performers by average score.
        ranked = sorted(
            ({'student': r['student'], 'average_score': r['average_score'],
              'credits': r['credits']} for r in bs['rows'] if r['average_score'] is not None),
            key=lambda r: r['average_score'], reverse=True)

        return {
            'exam': bs['exam'],
            'empty': False,
            'school': bs['school'],
            'subjects': subjects,
            'subject_summary': ss,
            'grade_order': bs['grade_order'],
            'grade_distribution': bs['grade_distribution'],
            'grade_distribution_pct': bs['grade_distribution_pct'],
            'difficulty': difficulty,
            'easiest': list(reversed(difficulty))[:5],
            'hardest': difficulty[:5],
            'score_stats': score_stats,
            'subject_stats': subject_stats,
            'top_performers': ranked[:5],
            'bottom_performers': list(reversed(ranked))[:5],
            'most_failed': sorted(
                ({'subject': s, **ss[s]} for s in subjects),
                key=lambda d: d['failed'], reverse=True)[:5],
            'credit_histogram': credit_histogram,
            'core': {
                'english_pct': _credit_rate('English Language'),
                'maths_pct': _credit_rate('Mathematics'),
                'both_pct': bs['school']['with_5_incl_core_pct'],
            },
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
        return MockWAECAnalytics._predict_from_progress(
            MockWAECAnalytics.get_student_progress(student_id, session_id))

    @staticmethod
    def subject_outlook(student_id, session_id=None):
        """Per-subject WAEC projection from the student's own Mock WAEC sittings
        (the most direct WAEC signal). Returns the structure the predictions page
        renders, or None when the student has no Mock WAEC results."""
        q = MockWAECResult.query.filter_by(student_id=student_id).join(MockWAECExam)
        if session_id:
            q = q.filter(MockWAECExam.session_id == session_id)
        rows = q.order_by(MockWAECExam.exam_number).all()
        if not rows:
            return None

        by_subject = {}
        for r in rows:
            if r.score is not None:
                by_subject.setdefault(r.subject, []).append(r.score)

        preds = []
        for subject, scores in by_subject.items():
            if not scores:
                continue
            weighted = [(i + 1, s) for i, s in enumerate(scores)]   # recent weighted more
            tw = sum(w for w, _ in weighted)
            pscore = round(sum(w * s for w, s in weighted) / tw)
            trend = 'stable'
            if len(scores) >= 2:
                d = scores[-1] - scores[0]
                trend = 'improving' if d >= 4 else 'declining' if d <= -4 else 'stable'
            pscore = min(100, pscore + 3) if trend == 'improving' else \
                max(0, pscore - 3) if trend == 'declining' else pscore
            conf = min(90, 55 + len(scores) * 10)
            preds.append({
                'subject': subject,
                'mock_average': round(sum(scores) / len(scores), 1),
                'predicted_score': pscore,
                'predicted_grade': waec_grade_from_score(pscore),
                'grade_range': {'best_case': waec_grade_from_score(max(scores)),
                                'worst_case': waec_grade_from_score(min(scores))},
                'confidence': conf,
                'confidence_level': 'High' if conf >= 75 else 'Medium' if conf >= 60 else 'Low',
                'trend': trend,
                'sittings': len(scores),
            })
        if not preds:
            return None
        preds.sort(key=lambda p: GRADE_POINTS.get(p['predicted_grade'], 9))

        grades = [p['predicted_grade'] for p in preds]
        credits = sum(1 for g in grades if g in PASS_GRADES)
        distinctions = sum(1 for g in grades if g in DISTINCTION_GRADES)
        fails = sum(1 for g in grades if g in ('E8', 'F9'))
        credited = {p['subject'] for p in preds if p['predicted_grade'] in PASS_GRADES}
        missing_core = [s for s in CORE_SUBJECTS if s not in credited]
        outlook = ('Excellent' if credits >= 8 else 'Good' if credits >= 6
                   else 'Fair' if credits >= 5 else 'Needs Improvement')

        recs = []
        weak = [p['subject'] for p in preds if p['predicted_grade'] in ('D7', 'E8', 'F9')]
        if missing_core:
            recs.append({'priority': 'Critical', 'area': 'Core subjects',
                         'message': 'Projected below a credit in ' + ', '.join(missing_core)
                         + ' — both are required for admission.'})
        if weak:
            recs.append({'priority': 'High', 'area': 'At-risk subjects',
                         'message': 'Concentrate revision on ' + ', '.join(weak[:5]) + '.'})
        if not recs:
            recs.append({'priority': 'Maintain', 'area': 'On track',
                         'message': 'Keep up the current performance across subjects.'})

        return {
            'subject_predictions': preds,
            'total_subjects': len(preds),
            'summary': {
                'predicted_distinctions': distinctions,
                'predicted_credits': credits,
                'predicted_fails': fails,
                'overall_outlook': outlook,
                'likely_meets_university_requirement': credits >= 5 and not missing_core,
            },
            'recommendations': recs,
        }

    @staticmethod
    def _predict_from_progress(progress):
        """Pure prediction from a progress dict (reusable by a batched caller)."""
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
        # Project the core-subject requirement from the most recent sitting.
        missing_core = progress.get('latest_missing_core', list(CORE_SUBJECTS))
        meets_incl_core = predicted_credits >= 5 and not missing_core
        return {
            'predicted_credits': predicted_credits,
            'meets_minimum': predicted_credits >= 5,
            # The admission-grade projection: 5 credits *and* English & Maths.
            'meets_minimum_incl_core': meets_incl_core,
            'missing_core': missing_core,
            'quality': quality,
            'confidence': confidence,
            'trend': progress['trend'],
            'based_on_exams': exam_count,
        }
