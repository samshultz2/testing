"""Exam Trends page (results/analytics/trends) — every external exam's results across the years, and a
year-over-year comparison built for decisions.

One entry point, ``build(key, bid, year_a, year_b)``, for:
  * grade exams — WAEC, NECO, JSS3 (State BECE / NECO BECE), Basic 5/6
    (State Common Entrance / NCEE), each graded on its own scheme
    (``utils.insight_exams``);
  * JAMB — scores out of 400.

For each exam it returns per-year summaries, a comparison of two chosen years
(every measure with its change, a "real change or chance?" test, the year's
rank among all years, its streak, best year and 3-year average), subject-level
year-over-year movement, the grade / score-band shift, gender trends, a
next-year projection and a plain-language list of what to act on."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from statistics import mean, median, pstdev

from models import db, Student
from utils import exam_rules as R
from utils import stats_guard as SG


# --------------------------------------------------------------------------- #
# Which exams
# --------------------------------------------------------------------------- #
def _school_label(level, body):
    from models.models_school_exams import get_scheme
    return get_scheme(level, body).exam_name


def available(bid=None):
    """[(key, label, group)] for exams with results, in a sensible order."""
    from models import WAECResult, NECOResult, JAMBResult
    out = []

    def has(model):
        try:
            q = db.session.query(model.id)
            if bid is not None:
                q = q.join(Student, Student.id == model.student_id).filter(Student.branch_id == bid)
            return q.first() is not None
        except Exception:
            db.session.rollback()
            return False

    if has(WAECResult):
        out.append(('waec', 'WAEC', 'SSS3'))
    if has(NECOResult):
        out.append(('neco', 'NECO', 'SSS3'))
    if has(JAMBResult):
        out.append(('jamb', 'JAMB', 'SSS3'))
    try:
        from models.models_school_exams import SchoolExamResult as S
        from utils import school_exams as svc
        svc.ensure_school_exam_schema()
        q = db.session.query(S.level, S.body).distinct()
        if bid is not None:
            q = q.join(Student, Student.id == S.student_id).filter(Student.branch_id == bid)
        pairs = set(q.all())
        for level, group in (('jss3', 'JSS3'), ('basic6', 'Basic 5/6')):
            for body in ('state', 'federal'):
                if (level, body) in pairs:
                    out.append(('%s_%s' % (level, body), _school_label(level, body), group))
    except Exception:
        db.session.rollback()
    try:
        from models.mock_waec import MockWAECResult
        from models.mock_jamb import MockJAMBResult
        if has(MockWAECResult):
            out.append(('mock_waec', 'Mock WAEC', 'Mocks'))
        if has(MockJAMBResult):
            out.append(('mock_jamb', 'Mock JAMB', 'Mocks'))
    except Exception:
        db.session.rollback()
    return out


# --------------------------------------------------------------------------- #
# Mock exams: each sitting is one period ("2025/2026 · Mock 2"), in date order
# --------------------------------------------------------------------------- #
def _mock_periods(exam_model, result_model, bid):
    """[{id, label, short, session_id, number}] for sittings with results."""
    from models import AcademicSession
    q = db.session.query(result_model.mock_exam_id).distinct()
    if bid is not None:
        q = q.join(Student, Student.id == result_model.student_id).filter(Student.branch_id == bid)
    ids = {i for (i,) in q.all()}
    if not ids:
        return []
    exams = exam_model.query.filter(exam_model.id.in_(list(ids))).all()
    sess = {s.id: s.name for s in AcademicSession.query.filter(
        AcademicSession.id.in_({e.session_id for e in exams})).all()}
    exams.sort(key=lambda e: (e.exam_date, e.exam_number, e.id))
    return [{'id': e.id, 'label': '%s · %s' % (sess.get(e.session_id, ''), e.name),
             'short': '%s %s' % ((sess.get(e.session_id) or '')[-9:].replace('/20', '/'), 'M%d' % e.exam_number),
             'session_id': e.session_id, 'number': e.exam_number} for e in exams]


class _MockWAEC:
    """Mock WAEC graded like WAEC (A1–F9, 5 credits incl. English & Maths);
    a "year" is one mock sitting (its exam id)."""
    key, name, exam_name = 'mock_waec', 'Mock WAEC', 'Mock WAEC'
    benchmark_label = '5 credits incl. Eng & Maths'
    max_points = 9

    def rows(self, year=None, bid=None):
        from models.mock_waec import MockWAECResult as M
        q = db.session.query(M.student_id, M.mock_exam_id, M.subject, M.grade).filter(
            db.or_(M.is_absent.is_(None), M.is_absent == False))  # noqa: E712
        if year is not None:
            q = q.filter(M.mock_exam_id == year)
        if bid is not None:
            q = q.join(Student, Student.id == M.student_id).filter(Student.branch_id == bid)
        return [(sid, y, subj, R.norm_grade(g)) for sid, y, subj, g in q.all() if g]

    def canon(self, subject):
        return R.canonical_subject(subject)

    def points(self, g):
        return R.points(g)

    def status(self, grades):
        return R.five_credit_status(grades)


def _exam(key):
    from utils import insight_exams as IX
    if key == 'mock_waec':
        return _MockWAEC()
    if key == 'waec':
        return IX.waec()
    if key == 'neco':
        return IX.neco()
    level, body = key.split('_', 1)
    IX.svc_ensure()
    return IX.SchoolExam(level, body)


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _pct(k, n):
    return round(k / n * 100, 1) if n else None


def _gender(g):
    g = (g or '').strip().lower()
    return 'F' if g.startswith('f') else 'M' if g.startswith('m') else None


def _genders(ids):
    if not ids:
        return {}
    return {sid: _gender(g) for sid, g in
            db.session.query(Student.id, Student.gender).filter(Student.id.in_(list(ids))).all()}


def _kind(exam, g):
    if hasattr(exam, 'kind'):
        return exam.kind(g)
    g = R.norm_grade(g)
    if g in R.DISTINCTION_GRADES:
        return 'distinction'
    if g in R.CREDIT_GRADES:
        return 'credit'
    if g in R.ORDINARY_PASS_GRADES:
        return 'pass'
    return 'fail'


def _gtext(exam, g):
    return exam.grade_text(g) if hasattr(exam, 'grade_text') else R.norm_grade(g)


def _grade_order(exam):
    if hasattr(exam, 'schemes'):
        seen = []
        for sc in exam.schemes.values():
            for b in sc.bands:
                if b['grade'] not in seen:
                    seen.append(b['grade'])
        return seen
    return list(R.WAEC_GRADES)


def _grade_kinds(exam):
    if hasattr(exam, 'schemes'):
        out = {}
        for sc in exam.schemes.values():
            for b in sc.bands:
                out.setdefault(b['grade'], b['kind'])
        return out
    return {g: _kind(exam, g) for g in R.WAEC_GRADES}


def _core(subject):
    try:
        from models.models_school_exams import core_key
        k = core_key(subject)
        if k:
            return k
    except Exception:
        pass
    return R.core_key(subject)


# --------------------------------------------------------------------------- #
# Grade exams: one year
# --------------------------------------------------------------------------- #
def _grade_year(exam, year, bid):
    by_sid = defaultdict(dict)
    for sid, _y, subj, g in exam.rows(year, bid):
        if g and (g[1] if isinstance(g, tuple) else g):
            by_sid[sid][exam.canon(subj)] = g
    n = len(by_sid)
    if not n:
        return None
    gender = _genders(by_sid.keys())
    maxp = getattr(exam, 'max_points', 9) or 9
    entries = cred = dist = fail = 0
    pts = []
    meets = near = eng = mth = core = 0
    credit_counts = []
    grades = Counter()
    subj = defaultdict(lambda: {'n': 0, 'c': 0, 'd': 0, 'f': 0, 'pts': 0.0})
    gen = {'M': {'n': 0, 'meets': 0, 'e': 0, 'c': 0}, 'F': {'n': 0, 'meets': 0, 'e': 0, 'c': 0}}
    for sid, gm in by_sid.items():
        st = exam.status(gm)
        meets += st['meets']
        near += st['near']
        eng += st['english']
        mth += st['maths']
        core += st['english'] and st['maths']
        credit_counts.append(st['credits'])
        gx = gen.get(gender.get(sid))
        if gx is not None:
            gx['n'] += 1
            gx['meets'] += st['meets']
        for s, g in gm.items():
            k = _kind(exam, g)
            p = exam.points(g)
            entries += 1
            pts.append(p)
            cred += k in ('distinction', 'credit')
            dist += k == 'distinction'
            fail += k == 'fail'
            grades[_gtext(exam, g)] += 1
            row = subj[s]
            row['n'] += 1
            row['c'] += k in ('distinction', 'credit')
            row['d'] += k == 'distinction'
            row['f'] += k == 'fail'
            row['pts'] += p
            if gx is not None:
                gx['e'] += 1
                gx['c'] += k in ('distinction', 'credit')
    bands = Counter('0–2' if c <= 2 else '3–4' if c <= 4 else '5–6' if c <= 6 else '7+' for c in credit_counts)
    return {
        'year': year, 'n': n, 'entries': entries,
        'k': {'meets': meets, 'near': near, 'eng': eng, 'mth': mth, 'core': core,
              'cred': cred, 'dist': dist, 'fail': fail},
        'm': {
            'candidates': n,
            'benchmark_rate': _pct(meets, n), 'near_rate': _pct(near, n),
            'core_rate': _pct(core, n), 'eng_rate': _pct(eng, n), 'maths_rate': _pct(mth, n),
            'credit_rate': _pct(cred, entries), 'distinction_rate': _pct(dist, entries),
            'fail_rate': _pct(fail, entries),
            'avg_credits': round(mean(credit_counts), 2),
            'avg_points': round(mean(pts), 2) if pts else None,
            'boys_benchmark': _pct(gen['M']['meets'], gen['M']['n']),
            'girls_benchmark': _pct(gen['F']['meets'], gen['F']['n']),
            'gender_gap': (round(_pct(gen['F']['meets'], gen['F']['n']) - _pct(gen['M']['meets'], gen['M']['n']), 1)
                           if gen['M']['n'] and gen['F']['n'] else None),
        },
        'gender': gen,
        'grades': dict(grades),
        'bands': {b: bands.get(b, 0) for b in ('0–2', '3–4', '5–6', '7+')},
        'subjects': {s: {'n': v['n'], 'credit': _pct(v['c'], v['n']), 'dist': _pct(v['d'], v['n']),
                         'fail': _pct(v['f'], v['n']), 'avg_points': round(v['pts'] / v['n'], 2),
                         'kc': v['c']}
                     for s, v in subj.items()},
        'max_points': maxp,
    }


def _grade_measures(exam):
    bench = exam.benchmark_label
    return [
        # key, label, unit, good_up, (k, n) for the significance test, group, help
        ('candidates', 'Candidates', '', None, None, 'Cohort', 'How many sat the exam.'),
        ('benchmark_rate', 'Met the benchmark', '%', True, ('meets', 'n'), 'Outcomes', bench),
        ('near_rate', 'One grade short of the benchmark', '%', False, ('near', 'n'), 'Outcomes',
         'Would have met the benchmark with one more credit — the easiest wins.'),
        ('core_rate', 'Credit in English and Maths', '%', True, ('core', 'n'), 'Core subjects', ''),
        ('eng_rate', 'Credit in English', '%', True, ('eng', 'n'), 'Core subjects', ''),
        ('maths_rate', 'Credit in Maths', '%', True, ('mth', 'n'), 'Core subjects', ''),
        ('credit_rate', 'Credit rate (all papers)', '%', True, ('cred', 'entries'), 'Grades',
         'Share of all subject papers graded credit or better.'),
        ('distinction_rate', 'Distinction rate', '%', True, ('dist', 'entries'), 'Grades', ''),
        ('fail_rate', 'Fail rate', '%', False, ('fail', 'entries'), 'Grades', ''),
        ('avg_credits', 'Average credits per candidate', '', True, None, 'Grades', ''),
        ('avg_points', 'Average grade points', '', True, None, 'Grades',
         'Per paper, higher is better (out of %d).' % (getattr(exam, 'max_points', 9) or 9)),
        ('girls_benchmark', 'Girls meeting the benchmark', '%', True, None, 'Gender', ''),
        ('boys_benchmark', 'Boys meeting the benchmark', '%', True, None, 'Gender', ''),
        ('gender_gap', 'Gender gap (girls − boys)', ' pts', None, None, 'Gender',
         'Closer to zero is fairer.'),
    ]


# --------------------------------------------------------------------------- #
# JAMB: one year
# --------------------------------------------------------------------------- #
JAMB_BANDS = (('<160', 0, 159), ('160–199', 160, 199), ('200–249', 200, 249), ('250–299', 250, 299), ('300+', 300, 400))


def _jamb_years(bid):
    from models import JAMBResult as J
    q = db.session.query(J.exam_year).distinct()
    if bid is not None:
        q = q.join(Student, Student.id == J.student_id).filter(Student.branch_id == bid)
    return sorted({y for (y,) in q.all() if y})


def _jamb_year(year, bid, mock=False):
    if mock:
        from models.mock_jamb import MockJAMBResult as J
        q = J.query.filter(J.mock_exam_id == year)
    else:
        from models import JAMBResult as J
        q = J.query.filter(J.exam_year == year)
    if bid is not None:
        q = q.join(Student, Student.id == J.student_id).filter(Student.branch_id == bid)
    rows = [r for r in q.all() if r.total_score is not None]
    if not rows:
        return None
    gender = _genders({r.student_id for r in rows})
    sc = [r.total_score for r in rows]
    n = len(sc)
    subj = defaultdict(list)
    gen = {'M': [], 'F': []}
    for r in rows:
        g = gender.get(r.student_id)
        if g in gen:
            gen[g].append(r.total_score)
        for i in range(1, 5):
            name, v = getattr(r, 'subject%d' % i), getattr(r, 'subject%d_score' % i)
            if name and v is not None:
                subj[R.canonical_subject(name) if 'english' not in name.lower() else 'Use of English'].append(v)
    k = {'a200': sum(s >= 200 for s in sc), 'a250': sum(s >= 250 for s in sc),
         'a300': sum(s >= 300 for s in sc), 'b160': sum(s < 160 for s in sc)}
    return {
        'year': year, 'n': n, 'entries': n, 'k': k, 'scores': sc,
        'm': {
            'candidates': n, 'avg_score': round(mean(sc), 1), 'median_score': round(median(sc), 1),
            'top_score': max(sc), 'sd': round(pstdev(sc), 1) if n > 1 else 0,
            'above_200': _pct(k['a200'], n), 'above_250': _pct(k['a250'], n),
            'above_300': _pct(k['a300'], n), 'below_160': _pct(k['b160'], n),
            'boys_avg': round(mean(gen['M']), 1) if gen['M'] else None,
            'girls_avg': round(mean(gen['F']), 1) if gen['F'] else None,
            'gender_gap': (round(mean(gen['F']) - mean(gen['M']), 1) if gen['M'] and gen['F'] else None),
        },
        'gender': {g: {'n': len(v)} for g, v in gen.items()},
        'bands': {lab: sum(lo <= s <= hi for s in sc) for lab, lo, hi in JAMB_BANDS},
        'subjects': {s: {'n': len(v), 'avg': round(mean(v), 1), 'pass': _pct(sum(x >= 50 for x in v), len(v)),
                         'kc': sum(x >= 50 for x in v), 'scores': v}
                     for s, v in subj.items()},
    }


JAMB_MEASURES = [
    ('candidates', 'Candidates', '', None, None, 'Cohort', ''),
    ('avg_score', 'Average score', '', True, 'mean', 'Outcomes', 'Out of 400.'),
    ('median_score', 'Median score', '', True, None, 'Outcomes', 'Half scored above this.'),
    ('above_200', 'Scored 200 or more', '%', True, ('a200', 'n'), 'Outcomes', 'A common admission cut-off.'),
    ('above_250', 'Scored 250 or more', '%', True, ('a250', 'n'), 'Outcomes', 'Competitive courses.'),
    ('above_300', 'Scored 300 or more', '%', True, ('a300', 'n'), 'Outcomes', ''),
    ('below_160', 'Scored below 160', '%', False, ('b160', 'n'), 'Outcomes', 'Below most institutions\' minimum.'),
    ('top_score', 'Top score', '', True, None, 'Spread', ''),
    ('sd', 'Spread of scores (std. dev.)', '', None, None, 'Spread', 'Smaller = a more even cohort.'),
    ('girls_avg', 'Girls\' average', '', True, None, 'Gender', ''),
    ('boys_avg', 'Boys\' average', '', True, None, 'Gender', ''),
    ('gender_gap', 'Gender gap (girls − boys)', ' pts', None, None, 'Gender', 'Closer to zero is fairer.'),
]


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #
def _significance(spec, ya, yb):
    """{'label', 'real', 'p'} — is the change between two years real or chance?"""
    if spec is None:
        return None
    if spec == 'mean':
        a, b = ya['scores'], yb['scores']
        if len(a) < 2 or len(b) < 2:
            return {'label': 'Not enough data', 'real': False, 'p': None}
        se = math.sqrt(pstdev(a) ** 2 / len(a) + pstdev(b) ** 2 / len(b))
        p = 1.0 if se == 0 else round(math.erfc(abs(mean(b) - mean(a)) / se / math.sqrt(2)), 4)
    else:
        kk, nn = spec
        k1, n1 = ya['k'][kk], ya[nn] if nn != 'n' else ya['n']
        k2, n2 = yb['k'][kk], yb[nn] if nn != 'n' else yb['n']
        if nn == 'entries':
            n1, n2 = ya['entries'], yb['entries']
        p = SG.two_proportion_test(k1, n1, k2, n2)
        if p is None:
            return {'label': 'Not enough data', 'real': False, 'p': None}
    if min(ya['n'], yb['n']) < SG.MIN_GROUP_N:
        return {'label': 'Small cohort', 'real': False, 'p': p}
    if p < 0.05:
        return {'label': 'Real change', 'real': True, 'p': p}
    return {'label': 'Could be chance', 'real': False, 'p': p}


def _streak(series, good_up):
    """Consecutive years the measure has moved the good way, ending at the last."""
    if good_up is None or len(series) < 2:
        return 0
    s = 0
    for i in range(len(series) - 1, 0, -1):
        a, b = series[i - 1], series[i]
        if a is None or b is None or a == b:
            break
        if (b > a) == good_up:
            s += 1
        else:
            break
    return s


def _compare(measures, years, ya, yb):
    """Rows for the year-over-year table."""
    out = []
    order = [y['year'] for y in years]            # periods in time order (years or mock sittings)
    pos_b = order.index(yb['year'])
    ylist = years[:pos_b + 1]
    for key, label, unit, good_up, spec, group, help_text in measures:
        a, b = ya['m'].get(key), yb['m'].get(key)
        if a is None and b is None:
            continue
        series = [(y['year'], y['m'].get(key)) for y in years]
        vals = [(yr, v) for yr, v in series if v is not None]
        upto = [(y['year'], y['m'].get(key)) for y in ylist if y['m'].get(key) is not None]
        delta = round(b - a, 2 if unit == '' and isinstance(b, float) and key not in ('candidates',) else 1) \
            if a is not None and b is not None else None
        rel = round((b - a) / a * 100, 1) if a not in (None, 0) and b is not None else None
        if key == 'gender_gap' and a is not None and b is not None:
            mood = 'good' if abs(b) < abs(a) - .05 else 'bad' if abs(b) > abs(a) + .05 else 'flat'
        elif good_up is None or delta is None or abs(delta) < 0.05:
            mood = 'flat' if delta is not None and abs(delta) < 0.05 else 'neutral'
        else:
            mood = 'good' if (delta > 0) == good_up else 'bad'
        rank = None
        if good_up is not None and b is not None and len(vals) > 1:
            ordered = sorted((v for _y, v in vals), reverse=good_up)
            rank = ordered.index(b) + 1
        best = None
        if good_up is not None and vals:
            best = (max if good_up else min)(vals, key=lambda t: t[1])
        prior = [v for yr, v in upto if order.index(yr) < pos_b][-3:]
        out.append({
            'key': key, 'label': label, 'unit': unit, 'group': group, 'help': help_text, 'good_up': good_up,
            'a': a, 'b': b, 'delta': delta, 'rel': rel, 'mood': mood,
            'sig': _significance(spec, ya, yb) if delta not in (None, 0) else None,
            'rank': rank, 'of': len(vals), 'best': best,
            'avg3': round(mean(prior), 1) if prior else None,
            'streak': _streak([v for _y, v in upto], good_up),
            'series': series,
        })
    return out


def _subjects_yoy(years, ya, yb, grade=True):
    """Subject movement between the two years, with each subject's history."""
    names = sorted(set(ya['subjects']) | set(yb['subjects']))
    rate = 'credit' if grade else 'pass'
    out = []
    for s in names:
        a, b = ya['subjects'].get(s), yb['subjects'].get(s)
        hist = [(y['year'], (y['subjects'].get(s) or {}).get(rate)) for y in years]
        va, vb = (a or {}).get(rate), (b or {}).get(rate)
        delta = round(vb - va, 1) if va is not None and vb is not None else None
        sig = None
        if a and b and delta:
            p = SG.two_proportion_test(a['kc'], a['n'], b['kc'], b['n'])
            sig = ('Small group' if min(a['n'], b['n']) < SG.MIN_GROUP_N
                   else 'Real change' if p is not None and p < 0.05 else 'Could be chance')
        seq = [v for _y, v in hist if v is not None]
        trend = 'new'
        if len(seq) >= 3 and seq[-1] > seq[-2] > seq[-3]:
            trend = 'rising'
        elif len(seq) >= 3 and seq[-1] < seq[-2] < seq[-3]:
            trend = 'falling'
        elif len(seq) >= 2:
            trend = 'mixed'
        row = {'subject': s, 'core': bool(_core(s)), 'a': va, 'b': vb, 'delta': delta, 'sig': sig,
               'n_a': (a or {}).get('n'), 'n_b': (b or {}).get('n'), 'trend': trend, 'history': hist}
        if grade:
            row.update({'pts_a': (a or {}).get('avg_points'), 'pts_b': (b or {}).get('avg_points'),
                        'fail_b': (b or {}).get('fail'), 'dist_b': (b or {}).get('dist')})
        else:
            row.update({'avg_a': (a or {}).get('avg'), 'avg_b': (b or {}).get('avg')})
        out.append(row)
    out.sort(key=lambda r: (r['delta'] is None, -(r['delta'] or 0) if r['delta'] is not None else 0, r['subject']))
    return out


def _fmt(v, unit=''):
    if v is None:
        return '—'
    if unit == '%':
        return '%.1f%%' % v
    return ('%g' % round(v, 2)) + (unit if unit != '' else '')


def _actions(kind, cmp_rows, subjects, ya, yb, exam_label, period='year'):
    """[(tone, icon, title, detail)] — what to act on, then what is working."""
    act, win = [], []
    m = {r['key']: r for r in cmp_rows}
    head = m.get('benchmark_rate') or m.get('above_200')
    if head and head['delta'] is not None and head['mood'] == 'bad' and head['sig'] and head['sig']['real']:
        act.append(('bad', 'fa-triangle-exclamation', '%s fell %s points' % (head['label'], _fmt(abs(head['delta']))),
                    ('From %s to %s — a real drop, not chance. Review %s preparation'
                     + (' before the next sitting.' if period == 'sitting' else ' for the next cohort.'))
                    % (_fmt(head['a'], '%'), _fmt(head['b'], '%'), exam_label)))
    if kind == 'grade':
        near = yb['k']['near']
        if near:
            act.append(('warn', 'fa-bullseye', '%d candidate%s one grade short of the benchmark'
                        % (near, '' if near == 1 else 's'),
                        'One more credit each would lift the benchmark rate by %s points — target borderline '
                        'subjects early next session.' % _fmt(round(near / yb['n'] * 100, 1))))
        for key, name in (('eng_rate', 'English'), ('maths_rate', 'Maths')):
            r = m.get(key)
            if r and r['b'] is not None and r['b'] < 60:
                act.append(('warn', 'fa-book', 'Only %s got a credit in %s' % (_fmt(r['b'], '%'), name),
                            '%s is required for almost every admission; it caps the benchmark rate.' % name))
    else:
        r = m.get('below_160')
        if r and r['b'] and r['b'] >= 15:
            act.append(('warn', 'fa-arrow-down', '%s scored below 160' % _fmt(r['b'], '%'),
                        'Below most institutions\' minimum — plan extra CBT practice for this group.'))
    falling = [s for s in subjects if s['sig'] == 'Real change' and (s['delta'] or 0) < 0]
    for s in falling[:4]:
        act.append(('bad', 'fa-arrow-trend-down', '%s dropped %s points' % (s['subject'], _fmt(abs(s['delta']))),
                    '%s → %s %s rate; a real decline.' % (_fmt(s['a'], '%'), _fmt(s['b'], '%'),
                                                          'credit' if kind == 'grade' else '≥50')))
    streaky = [s for s in subjects if s['trend'] == 'falling' and s not in falling]
    for s in streaky[:3]:
        act.append(('warn', 'fa-chart-line', '%s has fallen 3 %ss running' % (s['subject'], period),
                    'Now %s. A sustained slide — check teaching, staffing and syllabus coverage.' % _fmt(s['b'], '%')))
    weak = sorted((s for s in subjects if s['b'] is not None and s['b'] < 50 and (s['n_b'] or 0) >= 5
                   and s not in falling and s not in streaky), key=lambda s: s['b'])
    if weak:
        act.append(('warn', 'fa-circle-exclamation', 'Below 50%% in %d subject%s' % (len(weak), '' if len(weak) == 1 else 's'),
                    ', '.join('%s (%s)' % (s['subject'], _fmt(s['b'], '%')) for s in weak[:5])))
    gap = m.get('gender_gap')
    if gap and gap['b'] is not None and abs(gap['b']) >= 10:
        who = 'girls' if gap['b'] > 0 else 'boys'
        act.append(('warn', 'fa-venus-mars', 'A %s-point gender gap in favour of %s' % (_fmt(abs(gap['b'])), who),
                    'Check whether the gap is real before acting — see the gender trend below.'))
    if ya['n'] and abs(yb['n'] - ya['n']) / ya['n'] >= .2:
        act.append(('info', 'fa-users', 'Cohort size changed %+d%%' % round((yb['n'] - ya['n']) / ya['n'] * 100),
                    '%d → %d candidates. Rates from very different cohorts compare less reliably.' % (ya['n'], yb['n'])))

    if head and head['mood'] == 'good' and head['delta']:
        win.append(('good', 'fa-arrow-trend-up', '%s up %s points' % (head['label'], _fmt(head['delta'])),
                    ('%s → %s%s.' % (_fmt(head['a'], '%'), _fmt(head['b'], '%'),
                                     (' — best %s on record' % period) if head['rank'] == 1 and head['of'] > 1 else ''))
                    + (' A real improvement.' if head['sig'] and head['sig']['real'] else '')))
    if head and head['streak'] >= 2:
        win.append(('good', 'fa-fire', '%d %ss of improvement in a row' % (head['streak'], period), head['label'] + '.'))
    rising = [s for s in subjects if s['sig'] == 'Real change' and (s['delta'] or 0) > 0]
    for s in rising[:4]:
        win.append(('good', 'fa-circle-check', '%s up %s points' % (s['subject'], _fmt(s['delta'])),
                    '%s → %s. Worth sharing what worked with other departments.' % (_fmt(s['a'], '%'), _fmt(s['b'], '%'))))
    return act, win


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def build(key, bid=None, year_a=None, year_b=None):
    exams = available(bid)
    keys = [k for k, _l, _g in exams]
    if not exams:
        return {'exams': [], 'empty': True}
    if key not in keys:
        key = keys[0]
    label = next(l for k, l, _g in exams if k == key)
    group = next(g for k, _l, g in exams if k == key)
    mock = key.startswith('mock_')
    periods = None
    if key in ('jamb', 'mock_jamb'):
        kind = 'jamb'
        if mock:
            from models.mock_jamb import MockJAMBExam, MockJAMBResult
            periods = _mock_periods(MockJAMBExam, MockJAMBResult, bid)
            years = [y for y in (_jamb_year(p['id'], bid, mock=True) for p in periods) if y]
        else:
            years = [y for y in (_jamb_year(yr, bid) for yr in _jamb_years(bid)) if y]
        measures = JAMB_MEASURES
        grade_order, grade_kinds, bench = [], {}, 'Scored 200 or more'
    else:
        kind = 'grade'
        exam = _exam(key)
        if mock:
            from models.mock_waec import MockWAECExam, MockWAECResult
            periods = _mock_periods(MockWAECExam, MockWAECResult, bid)
            order = [p['id'] for p in periods]
        else:
            order = sorted(exam.years())
        years = [y for y in (_grade_year(exam, yr, bid) for yr in order) if y]
        measures = _grade_measures(exam)
        grade_order, grade_kinds, bench = _grade_order(exam), _grade_kinds(exam), exam.benchmark_label
    years = years[-10:]
    ylist = [y['year'] for y in years]
    if periods:
        pmap = {p['id']: p for p in periods}
        labels = {y: pmap[y]['label'] for y in ylist}
        shorts = {y: pmap[y]['short'] for y in ylist}
    else:
        pmap = {}
        labels = shorts = {y: str(y) for y in ylist}
    res = {'exams': exams, 'key': key, 'label': label, 'group': group, 'kind': kind, 'years': ylist,
           'points': years, 'bench_label': bench, 'grade_order': grade_order, 'grade_kinds': grade_kinds,
           'empty': not years, 'mock': mock, 'labels': labels, 'shorts': shorts,
           'period': 'sitting' if mock else 'year'}
    if not years:
        return res
    yb = year_b if year_b in ylist else ylist[-1]
    earlier = ylist[:ylist.index(yb)]
    ya = year_a if year_a in earlier else (earlier[-1] if earlier else None)
    res.update({'year_a': ya, 'year_b': yb, 'earlier': earlier})
    # Quick comparisons: previous, 3 back, first, and (mocks) the same mock last session.
    quick = []
    if earlier:
        quick.append(('previous ' + res['period'], earlier[-1]))
        if len(earlier) >= 3:
            quick.append(('3 %ss back' % res['period'], earlier[-3]))
        if len(earlier) >= 2:
            quick.append(('first on record', earlier[0]))
        if mock:
            pb = pmap[yb]
            same = [p for p in earlier if pmap[p]['number'] == pb['number'] and pmap[p]['session_id'] != pb['session_id']]
            if same:
                quick.append(('same mock last session', same[-1]))
    res['quick'] = quick
    B = next(y for y in years if y['year'] == yb)
    A = next((y for y in years if y['year'] == ya), None)
    head_key = 'benchmark_rate' if kind == 'grade' else 'avg_score'
    proj = None if mock else SG.projection(
        [(y['year'], y['m'][head_key]) for y in years if y['m'].get(head_key) is not None],
        lo=0, hi=100 if kind == 'grade' else 400, cap=15 if kind == 'grade' else 25)
    # A straight line through two points says nothing; and tiny cohorts swing.
    if proj and (proj['years'] < 3 or B['n'] < SG.MIN_GROUP_N):
        proj = None
    res['projection'] = proj
    res['counts'] = {y['year']: y['n'] for y in years}
    res['head_key'] = head_key
    res['B'] = B
    res['A'] = A
    # Single-year view (nothing to compare against yet).
    if A is None:
        res['compare'] = _compare(measures, years, B, B)
        for r in res['compare']:
            r.update({'a': None, 'delta': None, 'rel': None, 'mood': 'neutral', 'sig': None})
        res['subjects'] = _subjects_yoy(years, {'subjects': {}}, B, grade=(kind == 'grade'))
        res['actions'], res['wins'] = [], []
        res['verdict'] = None
        return res
    cmp_rows = _compare(measures, years, A, B)
    subjects = _subjects_yoy(years, A, B, grade=(kind == 'grade'))
    res['compare'] = cmp_rows
    res['subjects'] = subjects
    res['actions'], res['wins'] = _actions(kind, cmp_rows, subjects, A, B, label, res['period'])
    scored = [r for r in cmp_rows if r['good_up'] is not None and r['group'] in ('Outcomes', 'Core subjects', 'Grades')]
    better = sum(r['mood'] == 'good' for r in scored)
    worse = sum(r['mood'] == 'bad' for r in scored)
    head = next((r for r in cmp_rows if r['key'] == ('benchmark_rate' if kind == 'grade' else 'avg_score')), None)
    small = min(A['n'], B['n']) < SG.MIN_GROUP_N
    head_real = bool(head and head['sig'] and head['sig']['real'])
    if small:
        tone, word = 'mixed', 'Too few candidates to judge'
    elif head_real and head['mood'] in ('good', 'bad'):
        # A real move in the headline measure decides the year.
        tone = head['mood']
        word = ('A stronger ' if tone == 'good' else 'A weaker ') + res['period']
        if (tone == 'good' and worse > better) or (tone == 'bad' and better > worse):
            tone, word = 'mixed', 'A mixed ' + res['period']
    elif better > worse * 2 and better >= 3 and not (head and head['mood'] == 'bad'):
        tone, word = 'good', 'A stronger ' + res['period']
    elif worse > better * 2 and worse >= 3 and not (head and head['mood'] == 'good'):
        tone, word = 'bad', 'A weaker ' + res['period']
    else:
        tone, word = 'mixed', 'A mixed ' + res['period']
    res['verdict'] = {'tone': tone, 'title': word, 'better': better, 'worse': worse, 'small': small,
                      'n_a': A['n'], 'n_b': B['n'],
                      'same': len(scored) - better - worse, 'head': head}
    # Grade / band shift (share of all papers, or of candidates for JAMB bands).
    if kind == 'grade':
        ta, tb = A['entries'] or 1, B['entries'] or 1
        res['grade_shift'] = [{'grade': g, 'kind': grade_kinds.get(g, 'fail'),
                               'a': round(A['grades'].get(g, 0) / ta * 100, 1),
                               'b': round(B['grades'].get(g, 0) / tb * 100, 1)} for g in grade_order]
    else:
        res['grade_shift'] = [{'grade': lab, 'kind': k, 'a': _pct(A['bands'][lab], A['n']), 'b': _pct(B['bands'][lab], B['n'])}
                              for (lab, _lo, _hi), k in zip(JAMB_BANDS, ('fail', 'pass', 'credit', 'credit', 'distinction'))]
    return res
