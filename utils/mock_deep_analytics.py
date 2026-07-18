"""Decision-grade deep analytics for a single Mock JAMB / Mock WAEC exam.

The mock modules already carry per-exam statistics (distributions, subject
averages, top/bottom performers). This adds the three dimensions a head-teacher
or exams officer actually acts on — **per subject**, **per teacher** and **per
class arm** — plus an evidence-based recommendation layer aimed at three
audiences (students, teachers, management).

Design principles
-----------------
* One engine, two exam kinds. Every candidate result is normalised into the
  same ``record`` shape (a student, their arm, and a list of subject entries
  scored 0-100 with a pass flag), so the subject/teacher/arm rollups are shared.
* Teacher attribution is *inferred*, never asserted: a mock subject is matched to
  the SSS3 ``ClassSubject`` teacher for the candidate's arm (falling back to the
  all-arms teacher, then the subject's sole teacher). Unmatched entries collect
  under "Unassigned" rather than being dropped.
* No single-metric judgements. A teacher verdict weighs mean, pass rate, spread
  vs the cohort *and* sample size, and — because this is one mock — never
  recommends disciplinary action; the strongest flag asks for support and says
  in writing that HR decisions need a multi-mock, value-added picture.

Query budget: a handful of batched fetches (results, enrolments, class-subject
teachers); no per-student / per-subject round-trips.
"""
from __future__ import annotations

import math
import re
import datetime

PASS_GRADES = {'A1', 'B2', 'B3', 'C4', 'C5', 'C6'}          # WAEC credit or better
DISTINCTION_GRADES = {'A1', 'B2', 'B3'}
JAMB_SUBJECT_PASS = 50           # a JAMB subject score (out of 100) counts as a pass
JAMB_SUBJECT_STRONG = 70
MIN_TEACHER_ENTRIES = 8          # below this a teacher verdict stays "watch the sample"

# ---------------------------------------------------------------------------
# small stats helpers
# ---------------------------------------------------------------------------

def _mean(xs):
    return round(sum(xs) / len(xs), 1) if xs else None


def _sd(xs):
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return round(math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs)), 1)


def _median(xs):
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else round((s[mid - 1] + s[mid]) / 2, 1)


def _rate(num, den):
    return round(100 * num / den, 1) if den else None


def _is_core(subject):
    s = (subject or '').upper()
    return 'ENGLISH' in s or 'MATH' in s


# ---------------------------------------------------------------------------
# subject-name normalisation (mock strings <-> ClassSubject names)
# ---------------------------------------------------------------------------

_ALIASES = {
    'english': 'english language', 'useofenglish': 'english language',
    'englishlanguage': 'english language', 'lang': 'english language',
    'maths': 'mathematics', 'math': 'mathematics', 'mathematic': 'mathematics',
    'furthermaths': 'further mathematics', 'furthermath': 'further mathematics',
    'bio': 'biology', 'chem': 'chemistry', 'phy': 'physics', 'physic': 'physics',
    'econs': 'economics', 'econ': 'economics', 'govt': 'government', 'gov': 'government',
    'lit': 'literature in english', 'literature': 'literature in english',
    'crs': 'christian religious studies', 'crk': 'christian religious studies',
    'irs': 'islamic religious studies', 'irk': 'islamic religious studies',
    'geo': 'geography', 'commerce': 'commerce', 'account': 'accounting',
    'accounts': 'accounting', 'financialaccounting': 'accounting', 'agric': 'agricultural science',
    'agriculture': 'agricultural science', 'civic': 'civic education', 'civics': 'civic education',
}


def _norm_subject(name):
    """Casefold + strip punctuation and map common Nigerian exam aliases to a
    canonical key, so 'Maths', 'MATHEMATICS ' and 'mathematics' all collide."""
    key = re.sub(r'[^a-z0-9]', '', (name or '').lower())
    return _ALIASES.get(key, key)


# ---------------------------------------------------------------------------
# class-arm mapping (reuse the cohort-aware helper)
# ---------------------------------------------------------------------------

def _arm_map(student_ids):
    from utils.exam_class_league import _arm_map as _am
    return {sid: (v[0] if v else None) for sid, v in _am(student_ids).items()}


# ---------------------------------------------------------------------------
# teacher attribution: (subject, arm) -> teacher_name
# ---------------------------------------------------------------------------

def _teacher_resolver(session_id):
    """Return ``resolve(subject_name, arm_label) -> teacher_name`` built from the
    SSS3 ``ClassSubject`` rows. Prefers the exact (subject, arm) teacher, then the
    all-arms teacher, then the subject's sole teacher; else ''."""
    from models import db, ClassSubject, Subject, Term
    from utils.helpers import get_sss3_class
    sss3 = get_sss3_class()
    if not sss3:
        return lambda subj, arm: ''

    term_ids = set()
    if session_id:
        term_ids = {t.id for t in Term.query.filter_by(session_id=session_id).all()}

    q = (db.session.query(ClassSubject, Subject.name)
         .join(Subject, Subject.id == ClassSubject.subject_id)
         .filter(ClassSubject.class_id == sss3.id))
    rows = q.all()
    # Prefer rows from the exam's session; fall back to all terms if none match.
    scoped = [(cs, nm) for cs, nm in rows if cs.term_id in term_ids] if term_ids else []
    use = scoped or rows

    by_subj_arm = {}      # (norm_subject, arm_label) -> teacher
    by_subj_all = {}      # norm_subject -> teacher (arm NULL)
    by_subj_any = {}      # norm_subject -> set of teachers
    for cs, subj_name in use:
        teacher = (cs.teacher_name or '').strip()
        if not teacher:
            continue
        key = _norm_subject(subj_name)
        by_subj_any.setdefault(key, set()).add(teacher)
        if cs.arm is not None:
            by_subj_arm[(key, cs.arm.name)] = teacher
        else:
            by_subj_all[key] = teacher

    def resolve(subject_name, arm_label):
        key = _norm_subject(subject_name)
        if arm_label and (key, arm_label) in by_subj_arm:
            return by_subj_arm[(key, arm_label)]
        if key in by_subj_all:
            return by_subj_all[key]
        teachers = by_subj_any.get(key)
        if teachers and len(teachers) == 1:
            return next(iter(teachers))
        return ''

    return resolve


# ---------------------------------------------------------------------------
# record extraction (normalise both exam kinds)
# ---------------------------------------------------------------------------

def _jamb_records(exam, allowed_ids):
    """One record per candidate: 4 subject entries scored /100 + a 0-400 total."""
    from models import MockJAMBResult, Student
    rows = (MockJAMBResult.query.filter_by(mock_exam_id=exam.id)
            .join(Student, Student.id == MockJAMBResult.student_id).all())
    records = []
    for r in rows:
        if allowed_ids is not None and r.student.branch_id not in allowed_ids:
            continue
        subs = []
        for i in (1, 2, 3, 4):
            nm = getattr(r, f'subject{i}')
            sc = getattr(r, f'subject{i}_score')
            if nm and sc is not None:
                subs.append({'subject': nm.strip(), 'score': int(sc),
                             'grade': None, 'passed': sc >= JAMB_SUBJECT_PASS,
                             'distinction': sc >= JAMB_SUBJECT_STRONG})
        records.append({
            'student_id': r.student_id, 'name': r.student.full_name,
            'progress_id': r.student_id, 'subjects': subs,
            'total': r.total_score, 'headline': r.total_score, 'credits': None,
        })
    return records


def _waec_records(exam, allowed_ids):
    """One record per candidate aggregating that student's subject rows."""
    from models import MockWAECResult, Student
    from models.mock_waec import waec_grade_from_score
    rows = (MockWAECResult.query.filter_by(mock_exam_id=exam.id)
            .join(Student, Student.id == MockWAECResult.student_id).all())
    by_student = {}
    for r in rows:
        if allowed_ids is not None and r.student.branch_id not in allowed_ids:
            continue
        d = by_student.setdefault(r.student_id, {'name': r.student.full_name, 'subs': []})
        grade = r.grade or waec_grade_from_score(r.score)
        sc = r.score if r.score is not None else 0
        d['subs'].append({'subject': (r.subject or '').strip(), 'score': int(sc),
                          'grade': grade, 'passed': grade in PASS_GRADES,
                          'distinction': grade in DISTINCTION_GRADES})
    records = []
    for sid, d in by_student.items():
        subs = d['subs']
        scores = [s['score'] for s in subs]
        credits = sum(1 for s in subs if s['passed'])
        records.append({
            'student_id': sid, 'name': d['name'], 'progress_id': sid,
            'subjects': subs, 'total': None, 'headline': _mean(scores) or 0,
            'credits': credits,
        })
    return records


# ---------------------------------------------------------------------------
# rollups
# ---------------------------------------------------------------------------

def _subject_band(pass_rate):
    if pass_rate is None:
        return ('unknown', 'No data')
    if pass_rate < 40:
        return ('critical', 'Critical')
    if pass_rate < 60:
        return ('weak', 'Needs work')
    if pass_rate < 80:
        return ('fair', 'Fair')
    return ('strong', 'Strong')


def _subject_league(records, kind):
    """Aggregate every subject entry across candidates."""
    acc = {}
    for rec in records:
        for s in rec['subjects']:
            key = s['subject']
            a = acc.setdefault(key, {'subject': key, 'scores': [], 'pass': 0,
                                     'dist': 0, 'grades': {}})
            a['scores'].append(s['score'])
            a['pass'] += 1 if s['passed'] else 0
            a['dist'] += 1 if s['distinction'] else 0
            if s['grade']:
                a['grades'][s['grade']] = a['grades'].get(s['grade'], 0) + 1
    out = []
    for a in acc.values():
        n = len(a['scores'])
        pr = _rate(a['pass'], n)
        band, band_label = _subject_band(pr)
        out.append({
            'subject': a['subject'], 'n': n, 'mean': _mean(a['scores']),
            'sd': _sd(a['scores']), 'min': min(a['scores']), 'max': max(a['scores']),
            'pass_rate': pr, 'distinction_rate': _rate(a['dist'], n),
            'band': band, 'band_label': band_label,
            'grades': a['grades'],
            'recommendation': _subject_reco(a['subject'], pr, _mean(a['scores']), band, kind),
        })
    out.sort(key=lambda r: (r['pass_rate'] if r['pass_rate'] is not None else 0))
    return out


def _subject_reco(subject, pass_rate, mean, band, kind):
    pass_word = 'credit' if kind == 'waec' else 'pass'
    if band == 'critical':
        return (f"Only {pass_rate}% reached {pass_word} in {subject} (mean {mean}). "
                f"Re-teach the core syllabus from first principles, add a weekly timed "
                f"drill and a compulsory clinic for the failing band; review the teacher's "
                f"scheme of work and pace.")
    if band == 'weak':
        return (f"{subject} is below par at {pass_rate}% {pass_word} (mean {mean}). "
                f"Target the 3-4 topics that cost the most marks with worked past-questions "
                f"and formative quizzes.")
    if band == 'fair':
        return (f"{subject} is holding at {pass_rate}% {pass_word}. Push the near-miss band "
                f"over the line with exam-technique coaching and marked mock questions.")
    return (f"{subject} is a strength ({pass_rate}% {pass_word}). Protect it, stretch the top "
            f"band toward distinctions and lend its method to weaker subjects.")


def _teacher_league(records, resolve, cohort_pass_rate):
    """Attribute every subject entry to a teacher and score their effectiveness."""
    from utils.results_analytics_org import resolve_teacher_staff
    acc = {}
    for rec in records:
        arm = rec.get('arm')
        for s in rec['subjects']:
            teacher = resolve(s['subject'], arm) or 'Unassigned'
            t = acc.setdefault(teacher, {'teacher': teacher, 'scores': [], 'pass': 0,
                                         'dist': 0, 'subjects': set(), 'students': set()})
            t['scores'].append(s['score'])
            t['pass'] += 1 if s['passed'] else 0
            t['dist'] += 1 if s['distinction'] else 0
            t['subjects'].add(s['subject'])
            t['students'].add(rec['student_id'])
    out = []
    for t in acc.values():
        n = len(t['scores'])
        pr = _rate(t['pass'], n)
        mean = _mean(t['scores'])
        delta = round(pr - cohort_pass_rate, 1) if (pr is not None and cohort_pass_rate is not None) else None
        flag, verdict, reco = _teacher_verdict(t['teacher'], mean, pr, n, delta,
                                               len(t['subjects']))
        staff_id = None
        if t['teacher'] != 'Unassigned':
            try:
                staff_id = resolve_teacher_staff(t['teacher'])
            except Exception:
                staff_id = None
        out.append({
            'teacher': t['teacher'], 'staff_id': staff_id,
            'subjects': sorted(t['subjects']), 'subject_count': len(t['subjects']),
            'students': len(t['students']), 'entries': n,
            'mean': mean, 'pass_rate': pr, 'distinction_rate': _rate(t['dist'], n),
            'delta': delta, 'flag': flag, 'verdict': verdict, 'recommendation': reco,
        })
    out.sort(key=lambda r: (r['pass_rate'] if r['pass_rate'] is not None else -1), reverse=True)
    return out


def _teacher_verdict(name, mean, pass_rate, entries, delta, subject_count):
    """Multi-indicator, non-disciplinary verdict for one mock.

    Returns (flag, verdict, recommendation). Even the weakest flag ('support')
    recommends coaching, and states in writing that any HR decision needs a
    multi-mock, value-added trend — never a single sitting.
    """
    if name == 'Unassigned':
        return ('unassigned', 'Not linked to a teacher',
                'Assign these subjects to a teacher in Class Subjects so their results '
                'roll up to a named staff member next time.')
    if entries < MIN_TEACHER_ENTRIES:
        return ('insufficient', f'Only {entries} results — read with caution',
                f'Too few marked scripts ({entries}) to judge {name} fairly. Treat the '
                f'numbers as indicative and confirm over the next mock.')
    pr = pass_rate or 0
    d = delta or 0
    if pr >= 75 and d >= 0:
        return ('strong', 'Strong — commend & learn from',
                f'{name} is delivering: {pr}% pass{f" ({d:+} vs cohort)" if delta is not None else ""}. '
                f'Recognise this publicly and have them share their scheme, pacing and '
                f'revision method with peers teaching weaker groups.')
    if pr >= 60:
        return ('solid', 'Solid — fine-tune',
                f'{name} is around the cohort line ({pr}% pass). Focus on the near-miss '
                f'band and exam technique to lift more candidates over the threshold.')
    if pr >= 45:
        return ('watch', 'Watch — targeted support',
                f'{name} is trailing at {pr}% pass{f" ({d:+} vs cohort)" if delta is not None else ""}. '
                f'Offer a peer observation, review the scheme of work and re-check the '
                f'topics costing the most marks. Re-measure next mock before drawing conclusions.')
    return ('support', 'Needs support — coach, do not conclude',
            f'{name} is well below the cohort at {pr}% pass. This is a coaching priority: '
            f'pair with a strong teacher, agree a recovery plan and monitor. Do NOT act on '
            f'this single mock — any HR decision needs a sustained, value-added trend across '
            f'several sittings and context (group ability, attendance, class size).')


def _arm_league(records, kind):
    acc = {}
    for rec in records:
        arm = rec.get('arm') or 'Unclassified'
        a = acc.setdefault(arm, {'arm': arm, 'headline': [], 'entries': 0, 'pass': 0,
                                 'credits': [], 'above200': 0, 'jamb': []})
        a['headline'].append(rec['headline'])
        for s in rec['subjects']:
            a['entries'] += 1
            a['pass'] += 1 if s['passed'] else 0
        if kind == 'jamb' and rec['total'] is not None:
            a['jamb'].append(rec['total'])
            a['above200'] += 1 if rec['total'] >= 200 else 0
        if kind == 'waec' and rec['credits'] is not None:
            a['credits'].append(rec['credits'])
    out = []
    for a in acc.values():
        n = len(a['headline'])
        pr = _rate(a['pass'], a['entries'])
        row = {'arm': a['arm'], 'students': n, 'pass_rate': pr,
               'mean_headline': _mean(a['headline'])}
        if kind == 'jamb':
            row['jamb_mean'] = _mean(a['jamb'])
            row['above_200_rate'] = _rate(a['above200'], len(a['jamb']))
            row['sort'] = row['jamb_mean'] if row['jamb_mean'] is not None else -1
        else:
            row['avg_credits'] = _mean(a['credits'])
            row['sort'] = row['avg_credits'] if row['avg_credits'] is not None else -1
        out.append(row)
    out.sort(key=lambda r: r['sort'], reverse=True)
    for r in out:
        r.pop('sort', None)
    return out


def _segments(records, kind):
    """Student segments needing attention or recognition, each with an action note."""
    honour, at_risk, critical = [], [], []
    for rec in records:
        base = {'student_id': rec['student_id'], 'name': rec['name']}
        if kind == 'jamb':
            tot = rec['total'] or 0
            weak = sorted([s for s in rec['subjects'] if not s['passed']],
                          key=lambda s: s['score'])
            weak_names = ', '.join(s['subject'] for s in weak[:2])
            if tot >= 250:
                honour.append({**base, 'metric': f'{tot}', 'note': 'On track for a top JAMB score — stretch toward 300+.'})
            elif tot < 180:
                critical.append({**base, 'metric': f'{tot}',
                                 'note': f'Below 180. Intensive support' + (f' in {weak_names}' if weak_names else '') + '.'})
            elif tot < 200:
                at_risk.append({**base, 'metric': f'{tot}',
                                'note': f'Just under 200' + (f' — shore up {weak_names}' if weak_names else '') + '.'})
        else:
            cr = rec['credits'] or 0
            core_ok = sum(1 for s in rec['subjects'] if _is_core(s['subject']) and s['passed'])
            weak = sorted([s for s in rec['subjects'] if not s['passed']],
                          key=lambda s: s['score'])
            weak_names = ', '.join(s['subject'] for s in weak[:2])
            if cr >= 5 and core_ok >= 2:
                honour.append({**base, 'metric': f'{cr} credits', 'note': 'Meets the admission threshold — aim for distinctions.'})
            elif cr < 2:
                critical.append({**base, 'metric': f'{cr} credits',
                                 'note': f'Far from 5 credits. Priority intervention' + (f' in {weak_names}' if weak_names else '') + '.'})
            elif cr < 5 or core_ok < 2:
                gap = 'missing a core credit (Eng/Maths)' if core_ok < 2 else f'{5 - cr} credit(s) short'
                at_risk.append({**base, 'metric': f'{cr} credits',
                                'note': f'{gap.capitalize()}' + (f' — focus {weak_names}' if weak_names else '') + '.'})
    honour.sort(key=lambda x: x['name'])
    at_risk.sort(key=lambda x: x['name'])
    critical.sort(key=lambda x: x['name'])
    return {'honour': honour, 'at_risk': at_risk, 'critical': critical}


# ---------------------------------------------------------------------------
# cohort KPIs + distribution
# ---------------------------------------------------------------------------

def _jamb_kpis(records):
    totals = [r['total'] for r in records if r['total'] is not None]
    n = len(totals)
    dist = [
        {'band': '300-400', 'count': sum(1 for s in totals if s >= 300)},
        {'band': '250-299', 'count': sum(1 for s in totals if 250 <= s < 300)},
        {'band': '200-249', 'count': sum(1 for s in totals if 200 <= s < 250)},
        {'band': '180-199', 'count': sum(1 for s in totals if 180 <= s < 200)},
        {'band': '0-179', 'count': sum(1 for s in totals if s < 180)},
    ]
    kpis = [
        {'label': 'Candidates', 'value': n, 'sub': 'sat this mock', 'tone': 'blue'},
        {'label': 'Mean score', 'value': _mean(totals) if n else '—', 'sub': 'out of 400', 'tone': 'teal'},
        {'label': '≥ 200', 'value': f'{_rate(sum(1 for s in totals if s >= 200), n)}%' if n else '—',
         'sub': 'admission-competitive', 'tone': 'green'},
        {'label': '≥ 250', 'value': f'{_rate(sum(1 for s in totals if s >= 250), n)}%' if n else '—',
         'sub': 'strong candidates', 'tone': 'amber'},
    ]
    return kpis, dist, _median(totals)


def _waec_kpis(records):
    n = len(records)
    creds = [r['credits'] or 0 for r in records]
    five_core = 0
    eng_pass = eng_tot = math_pass = math_tot = 0
    for r in records:
        core_ok = sum(1 for s in r['subjects'] if _is_core(s['subject']) and s['passed'])
        if (r['credits'] or 0) >= 5 and core_ok >= 2:
            five_core += 1
        for s in r['subjects']:
            up = s['subject'].upper()
            if 'ENGLISH' in up:
                eng_tot += 1; eng_pass += 1 if s['passed'] else 0
            elif 'MATH' in up:
                math_tot += 1; math_pass += 1 if s['passed'] else 0
    kpis = [
        {'label': 'Candidates', 'value': n, 'sub': 'sat this mock', 'tone': 'blue'},
        {'label': 'Avg credits', 'value': _mean(creds) if n else '—', 'sub': 'per candidate', 'tone': 'teal'},
        {'label': '5 credits + core', 'value': f'{_rate(five_core, n)}%' if n else '—',
         'sub': 'admission-eligible', 'tone': 'green'},
        {'label': 'English credit', 'value': f'{_rate(eng_pass, eng_tot)}%' if eng_tot else '—',
         'sub': 'core subject', 'tone': 'amber'},
        {'label': 'Maths credit', 'value': f'{_rate(math_pass, math_tot)}%' if math_tot else '—',
         'sub': 'core subject', 'tone': 'amber'},
    ]
    # grade distribution across all subject entries
    order = ['A1', 'B2', 'B3', 'C4', 'C5', 'C6', 'D7', 'E8', 'F9']
    counts = {g: 0 for g in order}
    for r in records:
        for s in r['subjects']:
            if s['grade'] in counts:
                counts[s['grade']] += 1
    dist = [{'grade': g, 'count': counts[g]} for g in order]
    return kpis, dist


# ---------------------------------------------------------------------------
# recommendations (bucketed for three audiences)
# ---------------------------------------------------------------------------

def _recommendations(kind, subjects, teachers, arms, segments, cohort_pass_rate):
    students, tstaff, mgmt = [], [], []

    def rec(bucket, tone, title, text):
        bucket.append({'tone': tone, 'title': title, 'text': text})

    pass_word = 'credit' if kind == 'waec' else 'pass'

    # --- students ---
    if segments['critical']:
        rec(students, 'negative', f"{len(segments['critical'])} candidate(s) in the danger zone",
            'Place these students on a named recovery plan now — daily supervised prep, '
            'a mentor, and a fortnightly check on the two weakest subjects.')
    if segments['at_risk']:
        rec(students, 'warning', f"{len(segments['at_risk'])} near the threshold",
            'A focused push closes the gap: exam-technique clinics and marked past-questions '
            'in their borderline subjects before the next sitting.')
    crit_subj = [s for s in subjects if s['band'] == 'critical']
    if crit_subj:
        rec(students, 'negative', 'Subjects failing most candidates',
            f"{', '.join(s['subject'] for s in crit_subj[:5])} sit below 40% {pass_word}. "
            f"Make these compulsory-clinic subjects for the whole cohort.")
    if segments['honour']:
        rec(students, 'positive', f"{len(segments['honour'])} high performers",
            'Stretch them with harder papers and a distinction target so the top end pulls the '
            'mean up rather than coasting.')

    # --- teachers ---
    strong_t = [t for t in teachers if t['flag'] == 'strong']
    if strong_t:
        rec(tstaff, 'positive', 'Commend & spread what works',
            f"{', '.join(t['teacher'] for t in strong_t[:5])} are outperforming the cohort. "
            f"Recognise them and have them mentor peers and share schemes/revision plans.")
    support_t = [t for t in teachers if t['flag'] in ('watch', 'support')]
    if support_t:
        rec(tstaff, 'warning', 'Coaching priorities (not verdicts)',
            f"{', '.join(t['teacher'] for t in support_t[:5])} are trailing the cohort. Provide "
            f"peer observation, scheme review and a recovery plan — and re-measure across the "
            f"next mock. Do not act on one sitting alone.")
    unassigned = [t for t in teachers if t['flag'] == 'unassigned']
    if unassigned:
        rec(tstaff, 'insight', 'Link subjects to teachers',
            'Some subject results have no teacher attached. Set the teacher on each SSS3 '
            'Class Subject so effectiveness rolls up to named staff next time.')

    # --- management ---
    if len(arms) >= 2:
        best, worst = arms[0], arms[-1]
        key = 'jamb_mean' if kind == 'jamb' else 'avg_credits'
        bv, wv = best.get(key), worst.get(key)
        if bv is not None and wv is not None and bv != wv:
            rec(mgmt, 'insight', 'Close the arm gap',
                f"{best['arm']} ({bv}) is ahead of {worst['arm']} ({wv}). Investigate teaching, "
                f"streaming and revision differences and level up the weaker arm — or re-balance "
                f"groups so no arm is starved of strong teaching.")
    if crit_subj:
        rec(mgmt, 'negative', 'Curriculum & resourcing review',
            f"Persistently weak subjects ({', '.join(s['subject'] for s in crit_subj[:5])}) warrant "
            f"a department review: syllabus coverage vs the exam, textbook/lab resourcing, and "
            f"teacher CPD.")
    if cohort_pass_rate is not None and cohort_pass_rate < 50:
        rec(mgmt, 'negative', 'Cohort below 50% pass',
            f"Overall {pass_word} rate is {cohort_pass_rate}%. Treat this as a whole-school "
            f"priority: extra contact hours, a revision timetable and weekly tracked mocks to the "
            f"real exam.")
    rec(mgmt, 'insight', 'Track the trend, not one mock',
        'Decisions on students and staff should follow the trajectory across mocks and the '
        'value each teacher adds relative to intake — use the comparison and validation views '
        'alongside this report.')

    return {'students': students, 'teachers': tstaff, 'management': mgmt}


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------

def deep_analytics(kind, exam_id, allowed_ids=None):
    """Unified deep analytics for a Mock JAMB ('jamb') or Mock WAEC ('waec') exam.

    ``allowed_ids`` optionally restricts candidates to a set of branch ids.
    Returns a payload with ``meta``, ``kpis``, ``subjects``, ``teachers``,
    ``arms``, ``segments``, ``distribution`` and ``recommendations``; when there
    are no results ``meta.empty`` is True.
    """
    from models import db
    if kind == 'jamb':
        from models import MockJAMBExam as ExamModel
    else:
        from models import MockWAECExam as ExamModel
    exam = db.session.get(ExamModel, exam_id)
    if not exam:
        return None

    meta = {
        'kind': kind, 'exam_id': exam.id, 'exam_name': exam.display_name,
        'full_name': exam.name,
        'exam_date': exam.exam_date.strftime('%d %B %Y') if exam.exam_date else '',
        'session_name': exam.session.name if exam.session else '',
        'generated_at': datetime.datetime.now().strftime('%d %b %Y, %H:%M'),
        'empty': False,
    }

    records = (_jamb_records(exam, allowed_ids) if kind == 'jamb'
               else _waec_records(exam, allowed_ids))
    if not records:
        meta['empty'] = True
        return {'meta': meta, 'kpis': [], 'subjects': [], 'teachers': [], 'arms': [],
                'segments': {'honour': [], 'at_risk': [], 'critical': []},
                'distribution': [], 'recommendations': {'students': [], 'teachers': [], 'management': []}}

    # attach arms
    amap = _arm_map([r['student_id'] for r in records])
    for r in records:
        r['arm'] = amap.get(r['student_id'])

    # cohort pass rate across all subject entries
    all_entries = [s for r in records for s in r['subjects']]
    cohort_pass_rate = _rate(sum(1 for s in all_entries if s['passed']), len(all_entries))

    subjects = _subject_league(records, kind)
    resolve = _teacher_resolver(exam.session_id)
    teachers = _teacher_league(records, resolve, cohort_pass_rate)
    arms = _arm_league(records, kind)
    segments = _segments(records, kind)

    if kind == 'jamb':
        kpis, distribution, median = _jamb_kpis(records)
        meta['median'] = median
    else:
        kpis, distribution = _waec_kpis(records)

    meta['students'] = len(records)
    meta['cohort_pass_rate'] = cohort_pass_rate
    meta['subjects_count'] = len(subjects)
    meta['teachers_count'] = len([t for t in teachers if t['teacher'] != 'Unassigned'])
    meta['arms_count'] = len(arms)

    recommendations = _recommendations(kind, subjects, teachers, arms, segments, cohort_pass_rate)

    return {
        'meta': meta, 'kpis': kpis, 'subjects': subjects, 'teachers': teachers,
        'arms': arms, 'segments': segments, 'distribution': distribution,
        'recommendations': recommendations,
    }
