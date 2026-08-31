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


def term_maxes(term_id):
    """{assessment_type_id: max_score} for a term, or {} when the term uses the
    normal (global/subject) settings. This is the per-term override layer."""
    if not term_id:
        return {}
    from models import TermAssessmentSetting
    return {r.assessment_type_id: r.max_score
            for r in TermAssessmentSetting.query.filter_by(term_id=int(term_id)).all()}


def effective_max(subject, at, overrides=None, term=None, term_settings=None):
    """Effective max score for a subject + assessment type in a term.

    Precedence (highest first): a per-term setting for that term → the subject's
    own override → the global default. When no term is given (or the term has no
    settings) this behaves exactly as before, so existing terms are unaffected."""
    from models import SubjectAssessmentOverride
    term_id = term.id if hasattr(term, 'id') else term
    if term_id:
        if term_settings is None:
            term_settings = term_maxes(term_id)
        if at.id in term_settings:
            return term_settings[at.id]
    if overrides is None:
        overrides = {o.assessment_type_id: o.max_score
                     for o in SubjectAssessmentOverride.query.filter_by(
                         subject_id=subject.id, is_active=True).all()}
    return overrides.get(at.id, at.max_score)


def has_term_settings(term_id):
    return bool(term_maxes(term_id))


def save_term_settings(term_id, maxes):
    """Replace a term's assessment settings with ``maxes`` ({at_id: max_score}).
    An empty dict clears them (the term reverts to the normal global settings)."""
    from models import db, TermAssessmentSetting
    TermAssessmentSetting.query.filter_by(term_id=int(term_id)).delete()
    for at_id, mx in (maxes or {}).items():
        try:
            mx = int(mx)
        except (TypeError, ValueError):
            continue
        db.session.add(TermAssessmentSetting(term_id=int(term_id),
                                             assessment_type_id=int(at_id), max_score=max(0, mx)))
    db.session.commit()


def copy_term_settings(from_term_id, to_term_id):
    """Copy one term's assessment settings onto another. Returns rows copied."""
    src = term_maxes(from_term_id)
    if not src:
        return 0
    save_term_settings(to_term_id, src)
    return len(src)


def default_maxes():
    """The global default {at_id: max_score} for all active assessment types —
    the starting point when a term has no settings yet."""
    from models import AssessmentType
    return {at.id: at.max_score
            for at in AssessmentType.query.filter_by(is_active=True).order_by(AssessmentType.order).all()}


def subject_columns(subject, term=None):
    """Ordered [(assessment_type, max)] for a subject in a term, skipping excluded
    (max 0) columns. Honours per-term settings when the term has any."""
    from models import AssessmentType, SubjectAssessmentOverride
    # Deterministic order (id breaks ties on equal ``order``) so the score-sheet
    # columns are identical between the preview render and the save round-trip.
    types = AssessmentType.query.filter_by(is_active=True).order_by(
        AssessmentType.order, AssessmentType.id).all()
    overrides = {o.assessment_type_id: o.max_score
                 for o in SubjectAssessmentOverride.query.filter_by(
                     subject_id=subject.id, is_active=True).all()}
    term_id = term.id if hasattr(term, 'id') else term
    tset = term_maxes(term_id)
    cols = []
    for at in types:
        mx = effective_max(subject, at, overrides, term=term_id, term_settings=tset)
        if mx <= 0:
            continue
        cols.append((at, mx))
    return cols
