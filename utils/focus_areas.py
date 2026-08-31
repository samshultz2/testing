"""
Teaching focus-areas diagnostics for the current SSS3 cohort.

Squeezes actionable signal out of the active session's mock JAMB, mock WAEC and
(as it lands) real JAMB results to answer one question: *which subjects and
classes need teaching attention before the real exams, and what kind of fix?* —
not predicting a grade, but pointing at what to work on.

Everything is driven off the active session / active term, so each future SSS3
cohort gets this analysis fresh with no per-year hardcoding.

Signals produced (subject- and class-level, with the evidence behind each):
  * trend across mock 1→2→3 (improving / flat / declining / volatile);
  * severity — for WAEC this is the grade model's predicted P(miss a credit)
    (model-weighted; currently the prior until graduated cohorts exist), for
    JAMB the share of students below the per-subject concern line;
  * leverage — the "nudge group" sitting just below the credit/pass line, the
    best return on teaching time;
  * dispersion — whether weakness is whole-class or a draggable subgroup;
  * content-vs-format divergence — weak in both mock JAMB and mock WAEC = a
    content gap; weak in only one = an exam-format/style issue;
  * core-subject criticality (English & Maths gate admission);
  * at-risk individuals whose own trajectory is declining / sub-threshold;
  * a reality-vs-mocks check once real JAMB is entered for the cohort.

Topic/strand granularity is intentionally out of scope: the score-entered mocks
hold no per-question data. (CBT-delivered tests could feed a topic panel later
via CBTQuestion.topic + CBTAnswer.is_correct — a process choice, not a schema
change.)
"""
import statistics

from models.models import db
from models.mock_waec import (MockWAECExam, MockWAECResult, PASS_GRADES,
                              CORE_SUBJECTS, waec_grade_from_score)
from models.mock_jamb import MockJAMBExam, MockJAMBResult

# ---- thresholds / weights (documented heuristics) --------------------------
WAEC_CREDIT = 50          # C6 — a credit
WAEC_NUDGE_LOW = 45       # D7 band: one nudge below a credit
JAMB_CONCERN = 50         # per-subject (out of 100) line of concern
JAMB_NUDGE_LOW = 40       # just below the concern line
TREND_DELTA = 3.0         # mean-score move (points) that counts as a real trend
VOLATILE_SD = 8.0         # sd of consecutive deltas above which a subject is "volatile"
CORE_CRIT = 1.5           # criticality multiplier for English & Maths
LOW_N = 8                 # below this many measured students → low-confidence flag
DIVERGE = 0.40            # weakness gap that flags a format (not content) issue
REALITY_GAP = 5.0         # real-JAMB mean this far below the mock → "blind spot"

_TREND_FACTOR = {'declining': 1.25, 'volatile': 1.1, 'flat': 1.0,
                 'improving': 0.8, 'insufficient': 1.0}


# ---------------------------------------------------------------------------
# Phase 0 — cohort + melted long-form mock/real data for the active session
# ---------------------------------------------------------------------------

def _cohort(session_id, branch_id):
    """{student_id: {'student': s, 'class': arm_label}} for SSS3 students enrolled
    in the active term, branch-scoped. Class label groups the per-class views."""
    from models.models import (Student, ClassArmAssignment, StudentEnrollment,
                               ClassArm, SchoolClass, Term)
    from utils.helpers import get_active_term
    term = get_active_term()
    sss3 = SchoolClass.query.filter_by(name='SSS3').first()
    out = {}
    if not (term and sss3):
        return out
    # branch_id is resolved by the caller (request-scoped); None = all branches.
    q = ClassArmAssignment.query.filter_by(class_id=sss3.id, term_id=term.id)
    if branch_id is not None:
        q = q.filter(ClassArmAssignment.branch_id == branch_id)
    for caa in q.all():
        arm = db.session.get(ClassArm, caa.arm_id)
        label = arm.name if arm else 'SSS3'
        rows = (StudentEnrollment.query.filter_by(class_arm_assignment_id=caa.id, is_active=True)
                .join(Student).all())
        for en in rows:
            if en.student.is_active and not en.student.is_graduated:
                out[en.student_id] = {'student': en.student, 'class': label}
    return out


def _melt_mock_jamb(session_id, sids):
    """{subject: {exam_number: {sid: score}}} from mock JAMB sittings this session."""
    from utils.subject_match import canonical_subject
    melt = {}
    exams = (MockJAMBExam.query.filter_by(session_id=session_id)
             .order_by(MockJAMBExam.exam_number).all())
    for ex in exams:
        for r in ex.results.all():
            if r.student_id not in sids:
                continue
            for item in r.subjects_list:                       # [{'name','score'}]
                subj = canonical_subject(item['name']) or item['name']
                melt.setdefault(subj, {}).setdefault(ex.exam_number, {})[r.student_id] = item['score']
    return melt


def _melt_mock_waec(session_id, sids):
    """{subject: {exam_number: {sid: score}}} from mock WAEC sittings this session."""
    from utils.subject_match import canonical_subject
    melt = {}
    exams = (MockWAECExam.query.filter_by(session_id=session_id)
             .order_by(MockWAECExam.exam_number).all())
    exam_no = {e.id: e.exam_number for e in exams}
    if not exam_no:
        return melt
    rows = (MockWAECResult.query
            .filter(MockWAECResult.mock_exam_id.in_(list(exam_no)),
                    MockWAECResult.student_id.in_(list(sids) or [-1]),
                    MockWAECResult.score.isnot(None)).all())
    for r in rows:
        subj = canonical_subject(r.subject) or r.subject
        melt.setdefault(subj, {}).setdefault(exam_no[r.mock_exam_id], {})[r.student_id] = r.score
    return melt


def _real_jamb(session_id, sids):
    """{subject: {sid: score}} from real JAMB for this session's cohort (mapped by
    exam year), empty until real JAMB is entered."""
    from models.models import JAMBResult, AcademicSession
    from models.waec_grade_predict import _session_exam_year
    from utils.subject_match import canonical_subject
    sess = db.session.get(AcademicSession, session_id)
    year = _session_exam_year(sess)
    out = {}
    rows = JAMBResult.query.filter(JAMBResult.student_id.in_(list(sids) or [-1]))
    if year:
        rows = rows.filter(JAMBResult.exam_year == year)
    for r in rows.all():
        # Real JAMBResult stores subjects positionally (no subjects_list helper).
        for name, score in ((r.subject1, r.subject1_score), (r.subject2, r.subject2_score),
                            (r.subject3, r.subject3_score), (r.subject4, r.subject4_score)):
            if name and score is not None:
                subj = canonical_subject(name) or name
                out.setdefault(subj, {})[r.student_id] = score
    return out


# ---------------------------------------------------------------------------
# Phase 1 — per-subject aggregates (trend, dispersion, nudge group, movers)
# ---------------------------------------------------------------------------

def _latest_per_student(by_sitting):
    """{sid: score} from the latest sitting in which each student has a score."""
    latest = {}
    for exam_no in sorted(by_sitting):                         # ascending → last wins
        for sid, score in by_sitting[exam_no].items():
            latest[sid] = score
    return latest


def _trend(by_sitting):
    """Cohort trend label + the per-sitting mean series and slope."""
    nums = sorted(by_sitting)
    series = [round(statistics.mean(by_sitting[n].values()), 1) for n in nums
              if by_sitting[n]]
    if len(series) < 2:
        return {'label': 'insufficient', 'series': series, 'slope': 0.0, 'sittings': nums}
    slope = round(series[-1] - series[0], 1)
    deltas = [series[i + 1] - series[i] for i in range(len(series) - 1)]
    vol = statistics.pstdev(deltas) if len(deltas) > 1 else 0.0
    if vol > VOLATILE_SD and abs(slope) < TREND_DELTA:
        label = 'volatile'
    elif slope >= TREND_DELTA:
        label = 'improving'
    elif slope <= -TREND_DELTA:
        label = 'declining'
    else:
        label = 'flat'
    return {'label': label, 'series': series, 'slope': slope, 'sittings': nums}


def _movers(by_sitting, cohort, n=3):
    """Biggest decliners between a student's first and last sitting."""
    nums = sorted(by_sitting)
    if len(nums) < 2:
        return []
    first, last = by_sitting[nums[0]], by_sitting[nums[-1]]
    deltas = []
    for sid in set(first) & set(last):
        d = last[sid] - first[sid]
        deltas.append((d, sid))
    deltas.sort()                                              # most negative first
    out = []
    for d, sid in deltas[:n]:
        if d < 0 and sid in cohort:
            out.append({'name': cohort[sid]['student'].full_name, 'delta': round(d, 1)})
    return out


def _dispersion(scores):
    if len(scores) < 2:
        return 0.0
    return round(statistics.pstdev(scores), 1)


# ---------------------------------------------------------------------------
# Phase 4 — severity (model-weighted for WAEC), composite focus score
# ---------------------------------------------------------------------------

def _waec_severity(subject, latest_scores, branch_id, pairs, setting):
    """Mean predicted P(missing a credit) for a WAEC subject — driven by the grade
    model (currently its prior). Higher = more at risk of no credit."""
    from models.waec_grade_predict import predict_subject
    risks = []
    for sid, score in latest_scores.items():
        pred = predict_subject(score, subject, branch_id, setting=setting, pairs=pairs)
        risks.append(1.0 - pred['p_credit'])
    return round(statistics.mean(risks), 4) if risks else 0.0


def _jamb_severity(latest_scores):
    """Share of students below the per-subject JAMB concern line (0..1)."""
    if not latest_scores:
        return 0.0
    below = sum(1 for s in latest_scores.values() if s < JAMB_CONCERN)
    return round(below / len(latest_scores), 4)


def _nudge(latest_scores, low, high):
    """Students sitting in [low, high) — just below the line, best ROI."""
    return [sid for sid, s in latest_scores.items() if low <= s < high]


def _intervention(severity, dispersion, trend, fix_type):
    if trend == 'improving':
        return 'Maintain — responding to current teaching'
    if fix_type and fix_type != 'content gap':
        return 'Drill exam technique — ' + fix_type
    if severity >= 0.4 and dispersion >= 12:
        return 'Target a struggling subgroup (wide spread)'
    if severity >= 0.4:
        return 'Reteach the whole class (uniform weakness)'
    return 'Light reinforcement'


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_focus_report(session_id=None, branch_id=None):
    """The full teaching focus-areas report for the active session's SSS3 cohort.

    Returns a dict with a ranked `focus` list (each entry an evidence card), an
    `at_risk` panel and report-level meta/caveats. Branch-scoped when `branch_id`
    is given (a central/all-branches view passes None)."""
    from utils.helpers import get_active_session
    from models.models import AcademicSession
    from models.waec_grade_predict import training_pairs, active_setting

    sess = db.session.get(AcademicSession, session_id) if session_id else get_active_session()
    if not sess:
        return {'session': None, 'focus': [], 'at_risk': [], 'classes': [],
                'meta': {'reason': 'No active session.'}}
    session_id = sess.id

    cohort = _cohort(session_id, branch_id)
    sids = set(cohort)
    classes = sorted({c['class'] for c in cohort.values()})

    mj = _melt_mock_jamb(session_id, sids)
    mw = _melt_mock_waec(session_id, sids)
    rj = _real_jamb(session_id, sids)

    setting = active_setting()
    tpairs = training_pairs(branch_id)

    # Pre-compute per-subject latest scores and weakness for the divergence check.
    waec_weak, jamb_weak = {}, {}
    for subj, by in mw.items():
        waec_weak[subj] = _waec_severity(subj, _latest_per_student(by), branch_id,
                                         tpairs.get(subj, []), setting)
    for subj, by in mj.items():
        jamb_weak[subj] = _jamb_severity(_latest_per_student(by))

    focus = []
    focus += _subject_entries('mock_waec', mw, cohort, classes, branch_id, tpairs,
                              setting, waec_weak, jamb_weak, rj)
    focus += _subject_entries('mock_jamb', mj, cohort, classes, branch_id, tpairs,
                              setting, waec_weak, jamb_weak, rj)
    focus.sort(key=lambda e: e['focus_score'], reverse=True)

    at_risk = _at_risk(mw, mj, rj, cohort, branch_id, tpairs, setting)

    return {
        'session': sess.name,
        'cohort_size': len(cohort),
        'classes': classes,
        'focus': focus,
        'at_risk': at_risk,
        'has_real_jamb': bool(rj),
        'meta': {
            'mock_only': not rj,
            'caveat': 'All signals are mock-based unless a real-JAMB block is shown; '
                      'treat low-n subjects as indicative, not conclusive.',
        },
    }


def _subject_entries(source, melt, cohort, classes, branch_id, tpairs, setting,
                     waec_weak, jamb_weak, rj):
    is_waec = source == 'mock_waec'
    credit_line, nudge_low = ((WAEC_CREDIT, WAEC_NUDGE_LOW) if is_waec
                              else (JAMB_CONCERN, JAMB_NUDGE_LOW))
    entries = []
    for subj, by in melt.items():
        latest = _latest_per_student(by)
        if not latest:
            continue
        scores = list(latest.values())
        n = len(scores)
        trend = _trend(by)
        severity = (waec_weak.get(subj, 0.0) if is_waec else jamb_weak.get(subj, 0.0))
        nudge = _nudge(latest, nudge_low, credit_line)
        leverage = len(nudge) / n if n else 0.0
        is_core = subj in CORE_SUBJECTS
        crit = CORE_CRIT if is_core else 1.0

        # content-vs-format: only meaningful where the subject sits in both tests
        fix_type = None
        if subj in waec_weak and subj in jamb_weak:
            w, j = waec_weak[subj], jamb_weak[subj]
            if w >= DIVERGE and j >= DIVERGE:
                fix_type = 'content gap'
            elif w >= DIVERGE and j < DIVERGE:
                fix_type = 'WAEC theory/essay style'
            elif j >= DIVERGE and w < DIVERGE:
                fix_type = 'JAMB MCQ speed/format'

        dispersion = _dispersion(scores)
        focus_score = round(severity * crit * _TREND_FACTOR[trend['label']]
                            * (1 + 0.5 * leverage) * 100, 1)

        # reality-vs-mocks (JAMB only, when real results are in)
        reality = None
        if not is_waec and subj in rj:
            real_scores = list(rj[subj].values())
            if real_scores:
                rmean = round(statistics.mean(real_scores), 1)
                mmean = round(statistics.mean(scores), 1)
                reality = {'real_mean': rmean, 'mock_mean': mmean,
                           'delta': round(rmean - mmean, 1),
                           'blind_spot': (mmean - rmean) >= REALITY_GAP}
                if reality['blind_spot']:
                    focus_score = round(focus_score * 1.15, 1)

        entries.append({
            'source': source, 'subject': subj, 'is_core': is_core,
            'focus_score': focus_score, 'severity': severity,
            'mean': round(statistics.mean(scores), 1), 'dispersion': dispersion,
            'n': n, 'low_confidence': n < LOW_N,
            'trend': trend, 'nudge_group': len(nudge), 'leverage': round(leverage, 2),
            'movers': _movers(by, cohort),
            'fix_type': fix_type,
            'intervention': _intervention(severity, dispersion, trend['label'], fix_type),
            'per_class': _per_class(source, by, cohort, classes, branch_id, tpairs, setting),
            'reality': reality,
        })
    return entries


def _per_class(source, by, cohort, classes, branch_id, tpairs, setting):
    """Per-class mean + severity for one subject, with the class-vs-cohort delta."""
    is_waec = source == 'mock_waec'
    latest = _latest_per_student(by)
    cohort_mean = (round(statistics.mean(latest.values()), 1) if latest else 0.0)
    out = []
    for cl in classes:
        sub = {sid: s for sid, s in latest.items()
               if sid in cohort and cohort[sid]['class'] == cl}
        if not sub:
            continue
        out.append({'class': cl, 'n': len(sub),
                    'mean': round(statistics.mean(sub.values()), 1),
                    'delta_vs_cohort': round(statistics.mean(sub.values()) - cohort_mean, 1)})
    out.sort(key=lambda c: c['mean'])                          # weakest class first
    return out


# ---------------------------------------------------------------------------
# Phase 3 — at-risk individuals
# ---------------------------------------------------------------------------

def _at_risk(mw, mj, rj, cohort, branch_id, tpairs, setting):
    """Students whose own trajectory in a subject is failing — declining or
    consistently below the line — so the cohort average can't hide them."""
    from models.waec_grade_predict import predict_subject
    flags = []
    # WAEC: P(miss credit) high on the latest mock, or every sitting below credit
    for subj, by in mw.items():
        nums = sorted(by)
        latest = _latest_per_student(by)
        for sid, score in latest.items():
            if sid not in cohort:
                continue
            pred = predict_subject(score, subj, branch_id, setting=setting,
                                   pairs=tpairs.get(subj, []))
            traj = [by[n][sid] for n in nums if sid in by[n]]
            declining = len(traj) >= 2 and traj[-1] < traj[0] - TREND_DELTA
            all_below = traj and all(t < WAEC_CREDIT for t in traj)
            if pred['p_credit'] < 0.4 and (declining or all_below):
                flags.append({'student': cohort[sid]['student'].full_name,
                              'class': cohort[sid]['class'], 'source': 'Mock WAEC',
                              'subject': subj, 'trajectory': traj,
                              'p_credit': pred['p_credit'],
                              'reason': 'declining' if declining else 'always below credit'})
    # JAMB: latest below concern and not improving
    for subj, by in mj.items():
        nums = sorted(by)
        latest = _latest_per_student(by)
        for sid, score in latest.items():
            if sid not in cohort or score >= JAMB_CONCERN:
                continue
            traj = [by[n][sid] for n in nums if sid in by[n]]
            declining = len(traj) >= 2 and traj[-1] < traj[0]
            if declining or all(t < JAMB_CONCERN for t in traj):
                flags.append({'student': cohort[sid]['student'].full_name,
                              'class': cohort[sid]['class'], 'source': 'Mock JAMB',
                              'subject': subj, 'trajectory': traj, 'p_credit': None,
                              'reason': 'declining' if declining else 'always below pass'})
    # sort worst first: declining WAEC with lowest credit prob bubble up
    flags.sort(key=lambda f: (f['p_credit'] if f['p_credit'] is not None else 0.5))
    return flags
