"""
Assessment helpers — the per-subject Midterm/Practical (P/ME) rule.

When a subject has a practical: Midterm/Practical (P/ME) counts (default 10) and
the Theory paper (PBT/EXAM) is worth 40. When it does not: the Midterm column is
dropped and the Theory paper is worth 50. Both schemes total 100 with the CAs
(3x5) + Holiday Assignment (5) + CBT (30).

This is expressed through the existing ``SubjectAssessmentOverride`` rows so the
score-entry, report-card and broadsheet views (which already read overrides)
honour it automatically.
"""

MID_NAMES = {'MID', 'PME', 'P/ME', 'PRAC', 'PRACTICAL', 'MIDTERM'}
THEORY_NAMES = {'EXAM', 'PBT', 'THEORY', 'ESSAY'}
CBT_NAMES = {'CBT', 'OBJ', 'OBJECTIVE', 'OBJECTIVES'}

THEORY_WITH_PRACTICAL = 40
THEORY_WITHOUT_PRACTICAL = 50


def _code(at):
    return (at.short_name or at.name or '').upper().replace(' ', '')


def is_midterm(at):
    return _code(at) in MID_NAMES


def is_theory(at):
    return _code(at) in THEORY_NAMES


def is_cbt(at):
    return _code(at) in CBT_NAMES


def apply_practical(db, subject):
    """Sync the Midterm / Theory overrides for a subject from its has_practical flag."""
    from models import AssessmentType, SubjectAssessmentOverride

    types = AssessmentType.query.all()
    has_prac = bool(getattr(subject, 'has_practical', True))

    def set_override(at, value):
        ov = SubjectAssessmentOverride.query.filter_by(
            subject_id=subject.id, assessment_type_id=at.id).first()
        if ov:
            ov.max_score = value
            ov.is_active = True
        else:
            db.session.add(SubjectAssessmentOverride(
                subject_id=subject.id, assessment_type_id=at.id, max_score=value))

    def clear_override(at):
        ov = SubjectAssessmentOverride.query.filter_by(
            subject_id=subject.id, assessment_type_id=at.id).first()
        if ov:
            db.session.delete(ov)

    for at in types:
        if is_midterm(at):
            if has_prac:
                clear_override(at)        # use the global default (e.g. 10)
            else:
                set_override(at, 0)       # excluded
        elif is_theory(at):
            set_override(at, THEORY_WITH_PRACTICAL if has_prac else THEORY_WITHOUT_PRACTICAL)


def effective_max(subject, at, overrides=None):
    """Effective max score for a subject + assessment type."""
    from models import SubjectAssessmentOverride
    if overrides is None:
        overrides = {o.assessment_type_id: o.max_score
                     for o in SubjectAssessmentOverride.query.filter_by(
                         subject_id=subject.id, is_active=True).all()}
    return overrides.get(at.id, at.max_score)


def subject_columns(subject):
    """Ordered [(assessment_type, max)] for a subject, skipping excluded ones."""
    from models import AssessmentType, SubjectAssessmentOverride
    types = AssessmentType.query.filter_by(is_active=True).order_by(AssessmentType.order).all()
    overrides = {o.assessment_type_id: o.max_score
                 for o in SubjectAssessmentOverride.query.filter_by(
                     subject_id=subject.id, is_active=True).all()}
    cols = []
    for at in types:
        mx = effective_max(subject, at, overrides)
        if mx <= 0:
            continue
        cols.append((at, mx))
    return cols
