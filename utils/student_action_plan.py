"""Student action plan — a consolidated, plain-English narrative plus a
prioritised list of recommendations, synthesised from signals the platform
already computes (admission readiness, projected WAEC/JAMB, and the persisted
risk assessment). No new modelling: this is the presentation/synthesis layer
that turns the existing analytics into something a form teacher can act on.
"""
import json


def _latest_risk(student_id):
    from models.analytics_models import StudentRiskAssessment
    return (StudentRiskAssessment.query.filter_by(student_id=student_id)
            .order_by(StudentRiskAssessment.assessment_date.desc(),
                      StudentRiskAssessment.id.desc()).first())


def _risk_factors(risk):
    if not risk or not risk.risk_factors:
        return []
    try:
        val = json.loads(risk.risk_factors)
        return val if isinstance(val, list) else [str(val)]
    except Exception:
        return [risk.risk_factors]


_STATUS_LEAD = {
    'READY':       'On track for admission.',
    'CONDITIONAL': 'Close to admission-ready, with a few gaps to close.',
    'AT_RISK':     'At risk of missing admission requirements.',
    'NOT_READY':   'Not yet on an admission track — needs focused support.',
    'NO_DATA':     'No WAEC or JAMB signal recorded yet.',
}
_PRIORITY_ORDER = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}


def build_action_plan(student, session_id=None):
    """Return ``{status, headline, narrative, actions, readiness, risk_level}``.

    ``actions`` is a list of ``{area, recommendation, priority}`` sorted
    HIGH → LOW. Everything degrades gracefully when a student has no data."""
    from utils import exam_insights
    readiness = exam_insights.admission_readiness(student, session_id)
    status = readiness.get('status', 'NO_DATA')
    waec = readiness.get('waec') or {}
    jamb = readiness.get('jamb') or {}
    risk = _latest_risk(student.id)
    risk_level = getattr(risk, 'risk_level', None)
    factors = _risk_factors(risk)

    actions = []

    def add(area, rec, priority):
        actions.append({'area': area, 'recommendation': rec, 'priority': priority})

    if status == 'NO_DATA':
        add('Data', 'Record WAEC or Mock WAEC results so a readiness projection can be generated.', 'MEDIUM')
        add('Data', 'Record a Mock JAMB or JAMB result so a JAMB projection can be generated.', 'MEDIUM')

    # Turn each admission blocker into a concrete recommendation.
    credits = waec.get('credits')
    for b in readiness.get('blockers', []):
        low = b.lower()
        if 'credit' in low and 'needs 5' in low:
            add('WAEC credits', f'{b}. Prioritise credit passes in the weakest offered subjects.', 'HIGH')
        elif low.startswith('no ') and 'credit projected' in low:
            add('Core subject', f'{b}. Arrange targeted support — this is a core admission requirement.', 'HIGH')
        elif 'jamb' in low and 'below' in low:
            add('JAMB score', f'{b}. Add structured UTME practice and past-question drills.', 'HIGH')
        elif 'no waec signal' in low:
            add('Data', 'Record WAEC or Mock WAEC results so a projection can be generated.', 'MEDIUM')
        elif 'no jamb signal' in low:
            add('Data', 'Record a Mock JAMB or JAMB result so a projection can be generated.', 'MEDIUM')
        else:
            add('Admission', b, 'MEDIUM')

    # Risk-assessment factors (attendance, declining trend, multiple failures…).
    for f in factors:
        fl = f.lower()
        if 'attend' in fl:
            add('Attendance', f'{f}. Involve the form teacher / parents to lift attendance.', 'MEDIUM')
        elif 'declin' in fl or 'trend' in fl:
            add('Trajectory', f'{f}. Review recent mocks to arrest the decline early.', 'MEDIUM')
        elif 'fail' in fl:
            add('Weak subjects', f'{f}. Set up remedial classes for the affected subjects.', 'HIGH')
        else:
            add('Risk', f, 'MEDIUM')

    if status == 'READY':
        cats = readiness.get('eligible_categories') or []
        tail = (' Eligible course areas: ' + ', '.join(cats) + '.') if cats else ''
        add('Maintain', 'Performance meets requirements — sustain it and aim for stretch targets.' + tail, 'LOW')

    actions.sort(key=lambda a: _PRIORITY_ORDER.get(a['priority'], 1))

    # ---- narrative -------------------------------------------------------
    bits = [_STATUS_LEAD.get(status, '')]
    if waec:
        core_left = waec.get('missing_core') or []
        src = 'recorded WAEC' if waec.get('source') == 'actual' else 'mock projection'
        seg = f"Projected {credits} credit(s) ({src})"
        if core_left:
            seg += f", missing {', '.join(core_left)}"
        bits.append(seg + '.')
    if jamb:
        bits.append(f"Projected JAMB around {jamb.get('score')}.")
    if risk_level in ('RED', 'AMBER'):
        bits.append(f"Risk flag: {risk_level}.")
    if status == 'READY' and readiness.get('eligible_categories'):
        bits.append('Eligible for: ' + ', '.join(readiness['eligible_categories']) + '.')
    narrative = ' '.join(b for b in bits if b)

    return {
        'status': status,
        'headline': _STATUS_LEAD.get(status, ''),
        'narrative': narrative,
        'actions': actions,
        'readiness': readiness,
        'risk_level': risk_level,
    }
