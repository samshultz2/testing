"""Shared term report-card computation.

Used by the staff report-card view and the public (scratch-card) result checker
so both render identical numbers from a single source of truth.
"""
from models import (
    db, StudentEnrollment, ClassArmAssignment, ClassSubject, Subject, AssessmentType,
    SchoolSettings, StudentScore, GradeScale, TermSummary, Attendance, Week,
)

# Affective / behavioural traits shown on the report sheet, rated 1–5.
AFFECTIVE_TRAITS = [
    ('punctuality', 'Punctuality'), ('organization', 'Organization'),
    ('neatness', 'Neatness'), ('politeness', 'Politeness'), ('honesty', 'Honesty'),
    ('relationship', 'Relationship with others'), ('self_control', 'Self Control'),
    ('responsibility', 'Responsibility'), ('attentiveness', 'Attentiveness'),
    ('cooperation', 'Cooperation'), ('perseverance', 'Perseverance'),
    ('initiative', 'Initiative'),
]
AFFECTIVE_KEYS = [k for k, _ in AFFECTIVE_TRAITS]
RATING_LABELS = {5: 'Excellent', 4: 'Very Good', 3: 'Good', 2: 'Fair', 1: 'Poor'}


def active_traits():
    """Configured behavioural traits as [(key, label)] — falls back to defaults."""
    from models import BehaviouralTrait
    rows = (BehaviouralTrait.query.filter_by(is_active=True)
            .order_by(BehaviouralTrait.order, BehaviouralTrait.id).all())
    return [(r.key, r.label) for r in rows] if rows else AFFECTIVE_TRAITS


def _subject_totals(student_id, class_subjects, pass_mark):
    """(total_score, subjects_passed, subjects_failed) for one student."""
    total = passed = failed = 0
    for cs in class_subjects:
        subject_total = sum(
            s.score for s in StudentScore.query.filter_by(
                student_id=student_id, class_subject_id=cs.id).all() if s.score)
        if subject_total > 0:
            total += subject_total
            if subject_total >= pass_mark:
                passed += 1
            else:
                failed += 1
    return total, passed, failed


def _attendance_pct(enrollment_id, week_ids):
    """Term attendance % for an enrolment, or None when there are no records."""
    if not week_ids:
        return None
    recs = Attendance.query.filter(
        Attendance.enrollment_id == enrollment_id,
        Attendance.week_id.in_(week_ids)).all()
    if not recs:
        return None
    marks = sum((1 if a.morning_present else 0) + (1 if a.afternoon_present else 0)
                for a in recs)
    return round(marks / (len(recs) * 2) * 100, 1)


def _assign_ranks(rows, pos_key):
    """Competition ranking by average (ties share a rank: 1, 1, 3…)."""
    last_avg = None
    rank = 0
    for i, r in enumerate(sorted(rows, key=lambda x: x['average'], reverse=True)):
        if r['average'] != last_avg:
            rank = i + 1
            last_avg = r['average']
        r[pos_key] = rank


def compute_term_summaries(term_id, class_id):
    """Compute & persist TermSummary (totals, class/arm positions, attendance) for
    every active student in a class (across all its arms) for a term.

    Ranks by average score. Existing teacher/principal comments and promotion
    decisions are preserved. Returns the number of students processed.
    """
    assignments = ClassArmAssignment.query.filter_by(
        term_id=term_id, class_id=class_id).all()
    if not assignments:
        return 0
    arm_of = {a.id: a.arm_id for a in assignments}
    enrollments = StudentEnrollment.query.filter(
        StudentEnrollment.class_arm_assignment_id.in_(list(arm_of)),
        StudentEnrollment.is_active == True).all()
    if not enrollments:
        return 0

    pass_mark = SchoolSettings.get('pass_mark', 50)
    week_ids = [w.id for w in Week.query.filter_by(term_id=term_id).all()]

    cs_cache = {}

    def subjects_for(arm_id):
        if arm_id not in cs_cache:
            cs_cache[arm_id] = (ClassSubject.query.filter_by(
                term_id=term_id, class_id=class_id, is_active=True)
                .filter((ClassSubject.arm_id == None) | (ClassSubject.arm_id == arm_id)).all())
        return cs_cache[arm_id]

    rows = []
    for e in enrollments:
        css = subjects_for(arm_of[e.class_arm_assignment_id])
        total, passed, failed = _subject_totals(e.student_id, css, pass_mark)
        average = round(total / len(css), 2) if css else 0
        rows.append({
            'enrollment': e, 'subjects': len(css), 'total': total, 'average': average,
            'passed': passed, 'failed': failed,
            'attendance': _attendance_pct(e.id, week_ids),
        })

    # Class position (whole class) + arm position (within each arm), by average,
    # with competition ranking so ties share a position (e.g. 1, 1, 3).
    _assign_ranks(rows, 'pos_class')
    by_arm = {}
    for r in rows:
        by_arm.setdefault(r['enrollment'].class_arm_assignment_id, []).append(r)
    for arm_rows in by_arm.values():
        _assign_ranks(arm_rows, 'pos_arm')

    for r in rows:
        e = r['enrollment']
        ts = TermSummary.query.filter_by(student_id=e.student_id, term_id=term_id).first()
        if not ts:
            ts = TermSummary(student_id=e.student_id, term_id=term_id, enrollment_id=e.id)
            db.session.add(ts)
        ts.enrollment_id = e.id
        ts.total_subjects = r['subjects']
        ts.subjects_passed = r['passed']
        ts.subjects_failed = r['failed']
        ts.total_score = r['total']
        ts.average_score = r['average']
        ts.position_in_class = r['pos_class']
        ts.position_in_arm = r['pos_arm']
        if r['attendance'] is not None:
            ts.attendance_percentage = r['attendance']
    db.session.commit()
    return len(rows)


def build_report_card(student_id, term_id):
    """Return (enrollment, report_data) for a student in a term, or (None, None).

    report_data mirrors the structure used by templates/subjects/report_card.html.
    """
    enrollment = (StudentEnrollment.query.join(ClassArmAssignment).filter(
        StudentEnrollment.student_id == student_id,
        ClassArmAssignment.term_id == term_id,
        StudentEnrollment.is_active == True).first())
    if not enrollment:
        return None, None

    assignment = enrollment.class_arm_assignment
    class_subjects = (ClassSubject.query.filter_by(
        term_id=term_id, class_id=assignment.class_id, is_active=True)
        .filter((ClassSubject.arm_id == None) | (ClassSubject.arm_id == assignment.arm_id))
        .join(Subject).order_by(Subject.name).all())

    assessment_types = (AssessmentType.query.filter_by(is_active=True)
                        .order_by(AssessmentType.order, AssessmentType.id).all())
    pass_mark = SchoolSettings.get('pass_mark', 50)

    # Report-sheet columns: the CAs / Holiday Assignment etc. each show on their
    # own, but the exam papers — Mid-term (P.E/M.E), CBT and Theory — are summed
    # into a single "EXAM" column (no separate spaces for mid-term/CBT).
    from utils.assessments import is_midterm, is_cbt, is_theory
    exam_type_ids = [at.id for at in assessment_types
                     if is_midterm(at) or is_cbt(at) or is_theory(at)]
    display_columns = [{'key': at.id, 'label': at.short_name or at.name}
                       for at in assessment_types if at.id not in exam_type_ids]
    if exam_type_ids:
        display_columns.append({'key': 'EXAM', 'label': 'EXAM'})
    # Load the configured grade scale once (avoids a per-subject DB lookup) and
    # use it for both the printed grade key and grade/remark resolution.
    grade_bands = GradeScale.query.order_by(GradeScale.order, GradeScale.min_score.desc()).all()

    def grade_for(score):
        for b in grade_bands:
            if b.min_score <= score <= b.max_score:
                return b.grade, (b.remark or '')
        return '-', '-'

    subjects_data = []
    total_score = 0
    subjects_passed = 0
    subjects_failed = 0

    # All of this student's scores across the term's subjects in one query,
    # indexed by (class-subject, assessment) — was a query per subject.
    cs_ids = [cs.id for cs in class_subjects]
    score_map = {}
    if cs_ids:
        for s in StudentScore.query.filter(
                StudentScore.student_id == student_id,
                StudentScore.class_subject_id.in_(cs_ids)).all():
            score_map[(s.class_subject_id, s.assessment_type_id)] = s.score

    exam_id_set = set(exam_type_ids)
    for cs in class_subjects:
        row = {'subject': cs.subject, 'teacher': cs.teacher_name,
               'assessments': {}, 'cells': [], 'total': 0, 'grade': '-', 'remark': '-'}
        subject_total = 0
        for at in assessment_types:
            score = score_map.get((cs.id, at.id))
            row['assessments'][at.id] = score
            if score:
                subject_total += score
        # Per-display-column values (exam papers merged into one EXAM figure).
        exam_sum = sum(score_map.get((cs.id, tid)) or 0 for tid in exam_type_ids)
        for col in display_columns:
            if col['key'] == 'EXAM':
                row['cells'].append(exam_sum or None)
            else:
                row['cells'].append(score_map.get((cs.id, col['key'])))
        row['total'] = subject_total
        if subject_total > 0:
            row['grade'], row['remark'] = grade_for(subject_total)
            total_score += subject_total
            if subject_total >= pass_mark:
                subjects_passed += 1
            else:
                subjects_failed += 1
        subjects_data.append(row)

    average = round(total_score / len(class_subjects), 2) if class_subjects else 0
    term_summary = TermSummary.query.filter_by(
        student_id=student_id, term_id=term_id).first()

    # Marks obtainable/obtained + percentage (matches the printed report sheet).
    # Honour any per-term assessment settings (e.g. a term with no CBT).
    from utils.assessments import term_maxes as _term_maxes
    _tm = _term_maxes(term_id)
    obtainable_each = sum((_tm.get(at.id, at.max_score) or 0) for at in assessment_types) or 100
    scores_obtainable = len(class_subjects) * obtainable_each
    average_pct = round(total_score / scores_obtainable * 100, 2) if scores_obtainable else 0
    # Number in class = the roster of the student's own class arm.
    no_in_class = StudentEnrollment.query.filter_by(
        class_arm_assignment_id=assignment.id, is_active=True).count()

    report_data = {
        'enrollment': enrollment,
        'assignment': assignment,
        'subjects': subjects_data,
        'assessment_types': assessment_types,
        'columns': display_columns,
        'total_score': total_score,
        'average': average,
        'overall_grade': grade_for(average)[0] if average else '-',
        'grade_scale': grade_bands,
        'subjects_passed': subjects_passed,
        'subjects_failed': subjects_failed,
        'total_subjects': len(class_subjects),
        'term_summary': term_summary,
        'scores_obtainable': scores_obtainable,
        'scores_obtained': total_score,
        'average_pct': average_pct,
        'result_status': 'PASS' if average_pct >= pass_mark else 'FAIL',
        'no_in_class': no_in_class,
        'next_term_fees': SchoolSettings.get('next_term_fees'),
        'next_term_begins': SchoolSettings.get('next_term_begins'),
    }
    return enrollment, report_data
