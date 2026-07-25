"""
Mock JAMB Examination Models
Extends the existing JAMB model to support multiple mock examinations per session
"""
from datetime import datetime
from models.models import db


class MockJAMBExam(db.Model):
    """
    Represents a single Mock JAMB examination event.
    Schools typically conduct 3-4 mock exams before the real JAMB.
    """
    __tablename__ = 'mock_jamb_exams'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    exam_number = db.Column(db.Integer, nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('academic_sessions.id'), nullable=False)
    exam_date = db.Column(db.Date, nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))   # owning branch (for scoping)
    is_active = db.Column(db.Boolean, default=True)
    is_completed = db.Column(db.Boolean, default=False)
    is_published = db.Column(db.Boolean, default=False)   # students may sit it online
    duration_minutes = db.Column(db.Integer, default=120)  # the in-app sitting timer
    questions_per_subject = db.Column(db.Integer)  # legacy cap (NULL = use blueprint / all)
    blueprint = db.Column(db.Text)   # optional JSON {subject_key: {section: count}} per-mock override
    novel_title = db.Column(db.String(150))  # JAMB-approved novel for this mock's English paper
    source_mode = db.Column(db.String(10), default='bank')  # 'bank' (draw from bank) | 'manual'
    # Comma-separated SchoolClass names allowed to sit online. Empty/NULL = the
    # graduating SSS3 class only (the JAMB cohort) — the default.
    eligible_levels = db.Column(db.String(200))
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    session = db.relationship('AcademicSession', backref=db.backref('mock_jamb_exams', lazy='dynamic'))
    branch = db.relationship('Branch')
    results = db.relationship('MockJAMBResult', backref='exam', lazy='dynamic', cascade='all, delete-orphan')
    
    __table_args__ = (
        # Exam numbers are unique per session *within a branch*, so each branch
        # can run its own First/Second/... mock for the same session.
        db.UniqueConstraint('session_id', 'exam_number', 'branch_id', name='unique_mock_exam_per_session'),
    )
    
    @property
    def display_name(self):
        ordinals = {1: 'First', 2: 'Second', 3: 'Third', 4: 'Fourth'}
        ordinal = ordinals.get(self.exam_number, f'{self.exam_number}th')
        return f"{ordinal} Mock JAMB"
    
    @property
    def student_count(self):
        return self.results.count()
    
    @property
    def average_score(self):
        results = self.results.all()
        if not results:
            return 0
        return sum(r.total_score for r in results) / len(results)


class MockJAMBResult(db.Model):
    """Individual student results for a mock JAMB examination."""
    __tablename__ = 'mock_jamb_results'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    mock_exam_id = db.Column(db.Integer, db.ForeignKey('mock_jamb_exams.id'), nullable=False)
    total_score = db.Column(db.Integer, nullable=False)
    subject1 = db.Column(db.String(50))
    subject1_score = db.Column(db.Integer)
    subject2 = db.Column(db.String(50))
    subject2_score = db.Column(db.Integer)
    subject3 = db.Column(db.String(50))
    subject3_score = db.Column(db.Integer)
    subject4 = db.Column(db.String(50))
    subject4_score = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    student = db.relationship('Student', backref=db.backref('mock_jamb_results', lazy='dynamic'))
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'mock_exam_id', name='unique_student_mock_result'),
    )
    
    @property
    def subjects_list(self):
        subjects = []
        if self.subject1:
            subjects.append({'name': self.subject1, 'score': self.subject1_score or 0})
        if self.subject2:
            subjects.append({'name': self.subject2, 'score': self.subject2_score or 0})
        if self.subject3:
            subjects.append({'name': self.subject3, 'score': self.subject3_score or 0})
        if self.subject4:
            subjects.append({'name': self.subject4, 'score': self.subject4_score or 0})
        return subjects
    
    @property
    def performance_level(self):
        if self.total_score >= 300:
            return 'Excellent'
        elif self.total_score >= 250:
            return 'Very Good'
        elif self.total_score >= 200:
            return 'Good'
        elif self.total_score >= 180:
            return 'Fair'
        else:
            return 'Needs Improvement'
    
    @property
    def performance_color(self):
        colors = {
            'Excellent': 'success',
            'Very Good': 'info',
            'Good': 'primary',
            'Fair': 'warning',
            'Needs Improvement': 'danger'
        }
        return colors.get(self.performance_level, 'secondary')


class MockJAMBAnalytics:
    """Analytics and insights for Mock JAMB examinations."""
    
    @staticmethod
    def get_student_progress(student_id, session_id=None):
        query = MockJAMBResult.query.filter_by(student_id=student_id).join(MockJAMBExam)
        if session_id:
            query = query.filter(MockJAMBExam.session_id == session_id)
        results = query.order_by(MockJAMBExam.exam_number).all()
        return MockJAMBAnalytics._progress_from_results(student_id, results)

    @staticmethod
    def _progress_from_results(student_id, results):
        """Build the progress dict from already-loaded, exam-ordered results (each
        with its ``.exam`` available). Lets a cohort be computed from one batched
        query instead of one query per student."""
        if not results:
            return None

        progress_data = []
        prev_score = None
        
        for result in results:
            change = None
            if prev_score is not None:
                change = result.total_score - prev_score
            progress_data.append({
                'exam': result.exam.display_name,
                'exam_number': result.exam.exam_number,
                'exam_date': result.exam.exam_date,
                'score': result.total_score,
                'change': change,
                'subjects': result.subjects_list,
                'performance_level': result.performance_level
            })
            prev_score = result.total_score
        
        if len(progress_data) >= 2:
            first_score = progress_data[0]['score']
            last_score = progress_data[-1]['score']
            total_change = last_score - first_score
            trend = 'improving' if total_change > 0 else 'declining' if total_change < 0 else 'stable'
        else:
            total_change = 0
            trend = 'insufficient_data'
        
        return {
            'student_id': student_id,
            'progress': progress_data,
            'total_change': total_change,
            'trend': trend,
            'exam_count': len(progress_data),
            'average_score': sum(p['score'] for p in progress_data) / len(progress_data),
            'best_score': max(p['score'] for p in progress_data),
            'latest_score': progress_data[-1]['score'] if progress_data else 0
        }
    
    @staticmethod
    def get_exam_statistics(mock_exam_id):
        exam = db.session.get(MockJAMBExam, mock_exam_id)
        if not exam:
            return None
        
        results = exam.results.all()
        if not results:
            return {'exam': exam, 'student_count': 0, 'statistics': None}
        
        scores = [r.total_score for r in results]
        distribution = {
            '300-400': sum(1 for s in scores if s >= 300),
            '250-299': sum(1 for s in scores if 250 <= s < 300),
            '200-249': sum(1 for s in scores if 200 <= s < 250),
            '180-199': sum(1 for s in scores if 180 <= s < 200),
            '0-179': sum(1 for s in scores if s < 180)
        }
        
        subject_scores = {}
        for result in results:
            for subj in result.subjects_list:
                if subj['name'] not in subject_scores:
                    subject_scores[subj['name']] = []
                subject_scores[subj['name']].append(subj['score'])
        
        subject_analysis = []
        for subject, scores_list in subject_scores.items():
            subject_analysis.append({
                'subject': subject,
                'count': len(scores_list),
                'average': sum(scores_list) / len(scores_list),
                'max': max(scores_list),
                'min': min(scores_list),
                'above_50': sum(1 for s in scores_list if s >= 50),
                'above_70': sum(1 for s in scores_list if s >= 70)
            })
        
        return {
            'exam': exam,
            'student_count': len(results),
            'statistics': {
                'average': sum(scores) / len(scores),
                'max': max(scores),
                'min': min(scores),
                'median': sorted(scores)[len(scores) // 2],
                'above_200': sum(1 for s in scores if s >= 200),
                'above_250': sum(1 for s in scores if s >= 250),
                'above_300': sum(1 for s in scores if s >= 300)
            },
            'distribution': distribution,
            'subject_analysis': sorted(subject_analysis, key=lambda x: x['average'], reverse=True),
            'top_performers': sorted(results, key=lambda r: r.total_score, reverse=True)[:10]
        }
    
    @staticmethod
    def compare_mock_exams(session_id):
        exams = MockJAMBExam.query.filter_by(session_id=session_id).order_by(MockJAMBExam.exam_number).all()
        comparison = []
        for exam in exams:
            results = exam.results.all()
            if results:
                scores = [r.total_score for r in results]
                comparison.append({
                    'exam': exam,
                    'exam_number': exam.exam_number,
                    'student_count': len(results),
                    'average': sum(scores) / len(scores),
                    'max': max(scores),
                    'min': min(scores),
                    'above_200': sum(1 for s in scores if s >= 200),
                    'above_250_pct': round(sum(1 for s in scores if s >= 250) / len(scores) * 100, 1)
                })
        return comparison
    
    @staticmethod
    def predict_real_jamb(student_id, session_id):
        return MockJAMBAnalytics._predict_from_progress(
            MockJAMBAnalytics.get_student_progress(student_id, session_id))

    @staticmethod
    def _predict_from_progress(progress):
        """Pure prediction from a progress dict (so a batched caller can reuse the
        exact same maths without re-querying)."""
        if not progress or progress['exam_count'] < 2:
            return None

        # Recent exams are weighted more heavily than earlier ones.
        weights = [(i + 1, p['score']) for i, p in enumerate(progress['progress'])]
        total_weight = sum(w[0] for w in weights)
        predicted_score = sum(w[0] * w[1] for w in weights) / total_weight

        total_change = progress['total_change']
        if progress['trend'] == 'improving':
            predicted_score += min(10, total_change * 0.2)
        elif progress['trend'] == 'declining':
            predicted_score -= min(10, abs(total_change) * 0.1)

        predicted_score = max(0, min(400, round(predicted_score)))

        # Spread of recent scores feeds both the confidence level and the range.
        scores = [p['score'] for p in progress['progress']]
        spread = max(scores) - min(scores)
        margin = max(15, min(40, round(spread / 2) + 10))
        low = max(0, predicted_score - margin)
        high = min(400, predicted_score + margin)

        exam_count = progress['exam_count']
        confidence_level = min(95, 60 + exam_count * 8 - min(20, spread // 5))
        confidence_label = 'high' if exam_count >= 3 and spread < 50 else \
            'medium' if exam_count >= 2 else 'low'

        if progress['trend'] == 'improving':
            recommendation = (
                f"Scores are trending up (+{total_change}). Keep the current "
                f"study routine; a real JAMB score near {high} is within reach."
            )
        elif progress['trend'] == 'declining':
            recommendation = (
                f"Scores have slipped ({total_change}). Review weak subjects "
                f"now to recover before the real exam."
            )
        else:
            recommendation = (
                "Scores are stable. Targeting weaker subjects could push the "
                f"prediction above {predicted_score}."
            )

        return {
            'predicted_score': predicted_score,
            # Keys consumed by templates.
            'predicted_range': {'low': low, 'high': high},
            'improvement_trend': total_change,
            'confidence_level': confidence_level,
            'mock_count': exam_count,
            'recommendation': recommendation,
            # Legacy keys kept for backwards compatibility (API/older callers).
            'confidence': confidence_label,
            'based_on_exams': exam_count,
            'trend': progress['trend'],
            'range': {'low': low, 'high': high},
        }
    
    @staticmethod
    def get_improvement_recommendations(student_id, session_id):
        results = MockJAMBResult.query.filter_by(student_id=student_id).join(MockJAMBExam).filter(
            MockJAMBExam.session_id == session_id
        ).order_by(MockJAMBExam.exam_number.desc()).first()
        
        if not results:
            return None
        
        recommendations = []
        for subj in results.subjects_list:
            score = subj['score']
            subject = subj['name']
            
            if score < 40:
                priority = 'critical'
                rec = f'Focus heavily on {subject}. Consider extra tutoring.'
            elif score < 50:
                priority = 'high'
                rec = f'{subject} needs significant improvement. Review fundamentals.'
            elif score < 60:
                priority = 'medium'
                rec = f'{subject} is fair but can improve. Focus on weak topics.'
            elif score < 75:
                priority = 'low'
                rec = f'{subject} is good. Target challenging questions.'
            else:
                priority = 'none'
                rec = f'Excellent in {subject}. Keep it up!'
            
            recommendations.append({
                'subject': subject,
                'score': score,
                'priority': priority,
                'recommendation': rec
            })
        
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3, 'none': 4}
        recommendations.sort(key=lambda x: priority_order[x['priority']])
        return recommendations


# =============================================================================
# ONLINE MOCK JAMB — question bank (JAMB-standard structures) for the in-app
# sitting. Questions belong to a mock exam + subject; a question that needs a
# shared stimulus (a comprehension passage, cloze text, summary passage, oral
# register instruction) points at a MockJAMBPassage so it can never be served
# without its passage. Diagrams are supported on both passages and questions.
# =============================================================================

class MockJAMBPassage(db.Model):
    """A shared stimulus a group of Mock JAMB questions attach to — a
    comprehension passage, cloze text, summary passage or oral/register lead-in.
    JAMB English (and some others) present several questions against one
    passage."""
    __tablename__ = 'mock_jamb_passages'

    id = db.Column(db.Integer, primary_key=True)
    # NULL mock_exam_id => a reusable *bank* passage (drawn into mocks per the
    # JAMB blueprint). A set id is a legacy per-mock passage (still supported).
    mock_exam_id = db.Column(db.Integer, db.ForeignKey('mock_jamb_exams.id'), nullable=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    section = db.Column(db.String(40))           # JAMB paper section (e.g. comprehension/cloze)
    kind = db.Column(db.String(20), default='comprehension')   # comprehension/cloze/summary/oral/general
    title = db.Column(db.String(150))
    body = db.Column(db.Text)                    # the passage / instruction text
    image_url = db.Column(db.String(300))        # optional figure
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)

    exam = db.relationship('MockJAMBExam', backref=db.backref(
        'passages', lazy='dynamic', cascade='all, delete-orphan'))
    subject = db.relationship('Subject')

    # The sitting draws the pool by (subject_id, mock_exam_id); index it so a burst
    # of students starting an exam does index scans, not full-table scans.
    __table_args__ = (
        db.Index('ix_mock_jamb_passages_subject_pool', 'subject_id', 'mock_exam_id'),
    )

    KINDS = ('comprehension', 'cloze', 'summary', 'oral', 'general')

    @property
    def kind_label(self):
        return {'comprehension': 'Comprehension passage', 'cloze': 'Cloze passage',
                'summary': 'Summary passage', 'oral': 'Oral / register',
                'general': 'Shared instruction'}.get(self.kind, self.kind)


class MockJAMBQuestion(db.Model):
    """One objective Mock JAMB question (4 options, one correct), tagged by
    subject + syllabus topic/sub-topic, optionally attached to a passage and/or
    carrying a diagram image."""
    __tablename__ = 'mock_jamb_questions'

    id = db.Column(db.Integer, primary_key=True)
    # NULL mock_exam_id => a reusable *bank* question drawn into mocks per the
    # JAMB blueprint. A set id is a legacy per-mock question (still supported).
    mock_exam_id = db.Column(db.Integer, db.ForeignKey('mock_jamb_exams.id'), nullable=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    passage_id = db.Column(db.Integer, db.ForeignKey('mock_jamb_passages.id'))   # NULL = stand-alone
    section = db.Column(db.String(40))           # JAMB paper section (drives the blueprint draw)
    exam_body = db.Column(db.String(10), default='JAMB')   # JAMB / WAEC / Both
    difficulty = db.Column(db.String(10))        # optional: easy / medium / hard
    source = db.Column(db.String(20))            # provenance, e.g. 'paste' / 'manual' / 'import'
    source_ref = db.Column(db.String(40))        # external id (dedupe imports)
    exam_year = db.Column(db.String(8))          # the past-question year, when known (e.g. '2018')
    topic = db.Column(db.String(100))
    subtopic = db.Column(db.String(120))
    question_text = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(300))        # optional figure / diagram
    # True => the question refers to a figure we couldn't fetch; it is held out
    # of exams until an admin supplies the image (see the "needs images" queue).
    needs_image = db.Column(db.Boolean, default=False)
    option_a = db.Column(db.String(400))
    option_b = db.Column(db.String(400))
    option_c = db.Column(db.String(400))
    option_d = db.Column(db.String(400))
    correct_option = db.Column(db.String(1))     # 'A'/'B'/'C'/'D'
    marks = db.Column(db.Float, default=1)
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)

    exam = db.relationship('MockJAMBExam', backref=db.backref(
        'questions', lazy='dynamic', cascade='all, delete-orphan'))
    subject = db.relationship('Subject')
    passage = db.relationship('MockJAMBPassage', backref=db.backref(
        'questions', lazy='dynamic'))

    # The sitting draws the pool by (subject_id, mock_exam_id); index it so a burst
    # of students starting an exam does index scans, not full-table scans of a
    # multi-thousand-row bank.
    __table_args__ = (
        db.Index('ix_mock_jamb_questions_subject_pool', 'subject_id', 'mock_exam_id'),
    )

    @property
    def options(self):
        return [('A', self.option_a), ('B', self.option_b),
                ('C', self.option_c), ('D', self.option_d)]


class MockJAMBAttempt(db.Model):
    """A student's online sitting of a mock exam — the in-progress state and the
    graded totals. One per (student, exam); on submit the per-subject scores are
    also written to MockJAMBResult so all the existing analytics keep working."""
    __tablename__ = 'mock_jamb_attempts'

    id = db.Column(db.Integer, primary_key=True)
    mock_exam_id = db.Column(db.Integer, db.ForeignKey('mock_jamb_exams.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.now)
    submitted_at = db.Column(db.DateTime)
    status = db.Column(db.String(15), default='In progress')   # In progress / Submitted
    total_score = db.Column(db.Integer, default=0)             # out of 400
    duration_minutes = db.Column(db.Integer, default=120)      # snapshot of the exam's timer
    # The candidate's drawn paper, cached once at first render as JSON
    # {subject_id: [{"p": passage_id, "q": [qid,...]} | {"q": qid}, ...]}. Reused on
    # every reload/resume and at grading so the expensive pool draw runs ONCE per
    # student instead of on every page load — the key to surviving a mass start.
    paper = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)

    exam = db.relationship('MockJAMBExam', backref=db.backref(
        'attempts', lazy='dynamic', cascade='all, delete-orphan'))
    student = db.relationship('Student')
    answers = db.relationship('MockJAMBAnswer', backref='attempt', lazy='dynamic',
                              cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('mock_exam_id', 'student_id', name='unique_mock_attempt'),
    )


class MockJAMBAnswer(db.Model):
    """One saved answer within an online sitting."""
    __tablename__ = 'mock_jamb_answers'

    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey('mock_jamb_attempts.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('mock_jamb_questions.id'), nullable=False)
    selected_option = db.Column(db.String(1))
    is_correct = db.Column(db.Boolean, default=False)

    question = db.relationship('MockJAMBQuestion')

    __table_args__ = (
        db.UniqueConstraint('attempt_id', 'question_id', name='unique_mock_answer'),
    )


