"""External exams hub (/exam-levels/): every public exam grouped by class
level, with the latest year (or mock sitting) and how it moved since the one
before, plus a short "needs attention" list.

Each tile is built on its own and never takes the page down: a failing exam
shows as "No results yet" and the error is logged.
"""
from __future__ import annotations

import logging

from flask import url_for

from models import db

log = logging.getLogger(__name__)


def _delta(a, b):
    if a is None or b is None:
        return None
    return round(a - b, 1)


def _tone(rate, good=60, mid=40):
    if rate is None:
        return ''
    return 'good' if rate >= good else 'mid' if rate >= mid else 'bad'


def _blank(name, tag, href, add_href, add_label='Add results'):
    return {'name': name, 'tag': tag, 'href': href, 'add_href': add_href, 'add_label': add_label,
            'empty': True}


# --------------------------------------------------------------------------- #
# SSS3: WAEC / NECO (grades), JAMB (score), Mock WAEC / Mock JAMB (sittings)
# --------------------------------------------------------------------------- #
def _grade_years(model, bid):
    from models import Student
    q = db.session.query(model.exam_year).distinct()
    if bid is not None:
        q = q.join(Student, Student.id == model.student_id).filter(Student.branch_id == bid)
    return sorted({y for (y,) in q.all() if y})


def _grade_tile(key, name, model, href, add_href, analytics_href, bid):
    from utils import exam_yoy as Y
    years = _grade_years(model, bid)
    if not years:
        return _blank(name, 'Final', href, add_href)
    exam = Y._exam(key)
    cur = Y._grade_year(exam, years[-1], bid)
    prev = Y._grade_year(exam, years[-2], bid) if len(years) > 1 else None
    if not cur:
        return _blank(name, 'Final', href, add_href)
    m = cur['m']
    return {
        'name': name, 'tag': 'Final', 'period': str(years[-1]), 'prev_period': str(years[-2]) if prev else None,
        'value': m['benchmark_rate'], 'unit': '%', 'label': '5 credits incl. Eng & Maths', 'measure': '5-credit rate',
        'delta': _delta(m['benchmark_rate'], prev['m']['benchmark_rate']) if prev else None, 'delta_unit': ' pts',
        'meter': m['benchmark_rate'], 'tone': _tone(m['benchmark_rate']),
        'prev_n': prev['m']['candidates'] if prev else None,
        'facts': [('Sat', m['candidates']), ('Eng+Maths', '%s%%' % m['core_rate']),
                  ('Credits', '%s%%' % m['credit_rate'])],
        'near': cur['k']['near'], 'href': href, 'add_href': add_href, 'analytics': analytics_href,
    }


def _mock_waec_tile(bid):
    from models.mock_waec import MockWAECExam, MockWAECResult
    from utils import exam_yoy as Y
    href = url_for('mock_waec.index')
    periods = Y._mock_periods(MockWAECExam, MockWAECResult, bid)
    if not periods:
        return _blank('Mock WAEC', 'Mock', href, url_for('mock_waec.create_exam'), 'New mock')
    exam = Y._MockWAEC()
    last = periods[-1]
    cur = Y._grade_year(exam, last['id'], bid)
    prev = Y._grade_year(exam, periods[-2]['id'], bid) if len(periods) > 1 else None
    if not cur:
        return _blank('Mock WAEC', 'Mock', href, url_for('mock_waec.create_exam'), 'New mock')
    m = cur['m']
    return {
        'name': 'Mock WAEC', 'tag': 'Mock', 'period': last['label'].split(' · ')[-1],
        'prev_period': periods[-2]['label'].split(' · ')[-1] if prev else None,
        'value': m['benchmark_rate'], 'unit': '%', 'label': '5 credits incl. Eng & Maths', 'measure': '5-credit rate',
        'delta': _delta(m['benchmark_rate'], prev['m']['benchmark_rate']) if prev else None, 'delta_unit': ' pts',
        'meter': m['benchmark_rate'], 'tone': _tone(m['benchmark_rate']),
        'prev_n': prev['m']['candidates'] if prev else None,
        'facts': [('Sat', m['candidates']), ('Eng+Maths', '%s%%' % m['core_rate']),
                  ('Mocks', len(periods))],
        'near': cur['k']['near'], 'href': url_for('mock_waec.view_exam', exam_id=last['id']),
        'add_href': url_for('mock_waec.create_exam'), 'add_label': 'New mock', 'analytics': href,
    }


def _jamb_tile(bid):
    from utils import exam_yoy as Y
    href = url_for('results.jamb_list')
    years = Y._jamb_years(bid)
    cur = Y._jamb_year(years[-1], bid) if years else None
    if not cur:
        return _blank('JAMB (UTME)', 'Final', href, url_for('results.add_jamb'))
    prev = Y._jamb_year(years[-2], bid) if len(years) > 1 else None
    m = cur['m']
    return {
        'name': 'JAMB (UTME)', 'tag': 'Final', 'period': str(years[-1]),
        'prev_period': str(years[-2]) if prev else None,
        'value': m['avg_score'], 'unit': '/400', 'label': 'average score', 'measure': 'average score',
        'delta': _delta(m['avg_score'], prev['m']['avg_score']) if prev else None, 'delta_unit': '',
        'meter': m['above_200'], 'prev_n': prev['m']['candidates'] if prev else None,
        'tone': _tone(m['above_200'], 70, 45),
        'facts': [('Sat', m['candidates']), ('200+', '%s%%' % m['above_200']),
                  ('Top', m['top_score'])],
        'low': cur['k']['b160'], 'href': href + '?year=%d' % years[-1],
        'add_href': url_for('results.add_jamb'), 'analytics': href,
    }


def _mock_jamb_tile(bid):
    from models.mock_jamb import MockJAMBExam, MockJAMBResult
    from utils import exam_yoy as Y
    href = url_for('mock_jamb.index')
    periods = Y._mock_periods(MockJAMBExam, MockJAMBResult, bid)
    cur = Y._jamb_year(periods[-1]['id'], bid, mock=True) if periods else None
    if not cur:
        return _blank('Mock JAMB', 'Mock', href, url_for('mock_jamb.create_exam'), 'New mock')
    prev = Y._jamb_year(periods[-2]['id'], bid, mock=True) if len(periods) > 1 else None
    m = cur['m']
    return {
        'name': 'Mock JAMB', 'tag': 'Mock', 'period': periods[-1]['label'].split(' · ')[-1],
        'prev_period': periods[-2]['label'].split(' · ')[-1] if prev else None,
        'value': m['avg_score'], 'unit': '/400', 'label': 'average score', 'measure': 'average score',
        'delta': _delta(m['avg_score'], prev['m']['avg_score']) if prev else None, 'delta_unit': '',
        'meter': m['above_200'], 'prev_n': prev['m']['candidates'] if prev else None,
        'tone': _tone(m['above_200'], 70, 45),
        'facts': [('Sat', m['candidates']), ('200+', '%s%%' % m['above_200']),
                  ('Mocks', len(periods))],
        'low': cur['k']['b160'], 'href': url_for('mock_jamb.view_exam', exam_id=periods[-1]['id']),
        'add_href': url_for('mock_jamb.create_exam'), 'add_label': 'New mock', 'analytics': href,
    }


# --------------------------------------------------------------------------- #
# JSS3 (BECE) / Basic 5–6 (Common Entrance): state + federal bodies
# --------------------------------------------------------------------------- #
def _school_tile(level, body, meta):
    from utils import school_exams as svc
    bp = '%s_exams' % level
    name = meta['bodies'][body]['name']
    tag = body.title()
    href = url_for(bp + '.dashboard', body=body)
    add = url_for(bp + '.grid_entry', body=body)
    ys = svc.years_for(level, body)
    if not ys:
        return _blank(name, tag, href, add)
    st = svc.year_stats(level, body, ys[0])
    k = st['kpis']
    if not k.get('candidates'):
        return _blank(name, tag, href, add)
    pk = None
    if len(ys) > 1:
        pk = svc.year_stats(level, body, ys[1])['kpis']
        pk = pk if pk.get('candidates') else None
    rate = k.get('benchmark_rate')
    return {
        'name': name, 'tag': tag, 'period': str(ys[0]), 'prev_period': str(ys[1]) if pk else None,
        'value': rate, 'unit': '%', 'label': 'met the benchmark', 'measure': 'benchmark rate',
        'delta': _delta(rate, pk.get('benchmark_rate')) if pk else None, 'delta_unit': ' pts',
        'meter': rate, 'tone': _tone(rate), 'prev_n': pk['candidates'] if pk else None,
        'facts': [('Sat', k['candidates']), ('Eng+Maths', '%s%%' % k.get('core_credit_rate', 0)),
                  ('Avg', ('%s%%' % k['avg_pct']) if k.get('avg_pct') is not None else '—')],
        'href': url_for(bp + '.dashboard', body=body, year=ys[0]), 'add_href': add,
        'analytics': url_for(bp + '.analytics'),
    }


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception:            # noqa: BLE001 — one exam must not take the hub down
        log.exception('exam-levels tile failed: %s', getattr(fn, '__name__', fn))
        db.session.rollback()
        return None


def build(level_meta, bid=None):
    """{'levels': [...], 'attention': [...], 'totals': {...}} for the hub."""
    from models import WAECResult, NECOResult
    from utils import school_exams as svc

    def tile(fn, *a, fallback=None):
        return _safe(fn, *a) or fallback

    sss3 = [
        tile(_grade_tile, 'waec', 'WAEC (WASSCE)', WAECResult, url_for('results.waec_list'),
             url_for('results.add_waec'), url_for('results.analytics_hub'), bid,
             fallback=_blank('WAEC (WASSCE)', 'Final', url_for('results.waec_list'), url_for('results.add_waec'))),
        tile(_grade_tile, 'neco', 'NECO (SSCE)', NECOResult, url_for('results.neco_list'),
             url_for('results.add_neco'), url_for('results.analytics_hub'), bid,
             fallback=_blank('NECO (SSCE)', 'Final', url_for('results.neco_list'), url_for('results.add_neco'))),
        tile(_jamb_tile, bid, fallback=_blank('JAMB (UTME)', 'Final', url_for('results.jamb_list'),
                                              url_for('results.add_jamb'))),
        tile(_mock_waec_tile, bid, fallback=_blank('Mock WAEC', 'Mock', url_for('mock_waec.index'),
                                                   url_for('mock_waec.create_exam'), 'New mock')),
        tile(_mock_jamb_tile, bid, fallback=_blank('Mock JAMB', 'Mock', url_for('mock_jamb.index'),
                                                   url_for('mock_jamb.create_exam'), 'New mock')),
    ]
    levels = [{
        'key': 'sss3', 'title': 'SSS3', 'icon': 'fa-graduation-cap',
        'sub': 'School certificate and university entry',
        'class_note': None, 'exams': sss3,
        'links': [('fa-chart-pie', 'Analytics hub', url_for('results.analytics_hub')),
                  ('fa-chart-line', 'Year on year', url_for('results.analytics_trends')),
                  ('fa-bullseye', 'Readiness', url_for('results.readiness'))],
    }]
    for level in ('jss3', 'basic6'):
        meta = level_meta(level)
        bp = '%s_exams' % level
        cls = _safe(svc.find_level_class, level)
        students = _safe(lambda: len(svc.level_students(level, include_with_results=False))) or 0
        exams = [tile(_school_tile, level, b, meta,
                      fallback=_blank(meta['bodies'][b]['name'], b.title(), url_for(bp + '.dashboard', body=b),
                                      url_for(bp + '.grid_entry', body=b)))
                 for b in ('state', 'federal')]
        levels.append({
            'key': level, 'title': meta['class_label'], 'icon': meta['icon'],
            'sub': meta['long_name'].split(' — ')[-1],
            'class_name': cls.name if cls else None, 'students': students, 'missing_class': not cls,
            'exams': exams,
            'links': [('fa-gauge', 'Dashboard', url_for(bp + '.dashboard')),
                      ('fa-chart-pie', 'Analytics', url_for(bp + '.analytics')),
                      ('fa-scale-balanced', 'State vs Federal', url_for(bp + '.compare')),
                      ('fa-gear', 'Settings', url_for(bp + '.settings'))],
        })

    # A latest year with far fewer candidates than the one before is still being
    # entered: say so, and don't raise "fell by" alarms from a handful of rows.
    for lv in levels:
        for e in lv['exams']:
            if e.get('empty') or e.get('delta') is None:
                continue
            n, pn = e['facts'][0][1], e.get('prev_n')
            if pn and n < max(5, pn * .4):
                e['partial'] = True
                e['delta'] = None

    attention = []
    for lv in levels:
        if lv.get('missing_class'):
            attention.append({'tone': 'mid', 'icon': 'fa-circle-exclamation',
                              'text': 'No %s class found, so its candidates can\'t be listed.' % lv['title'],
                              'action': 'Set up classes', 'href': url_for('academics.classes_list')
                              if _has_endpoint('academics.classes_list') else None})
        for e in lv['exams']:
            if e.get('empty'):
                continue
            d = e.get('delta')
            drop = 5 if e['unit'] == '%' else 10
            if d is not None and d <= -drop:
                attention.append({'tone': 'bad', 'icon': 'fa-arrow-trend-down',
                                  'text': '%s %s: %s %s down %s%s on %s.' % (
                                      e['name'], e['period'], e['measure'], _num(e['value'], e['unit']),
                                      abs(d), e['delta_unit'] or ' pts', e['prev_period']),
                                  'action': 'See why', 'href': e.get('analytics') or e['href']})
            elif d is not None and d >= drop:
                attention.append({'tone': 'good', 'icon': 'fa-arrow-trend-up',
                                  'text': '%s %s: %s %s up %s%s on %s.' % (
                                      e['name'], e['period'], e['measure'], _num(e['value'], e['unit']),
                                      d, e['delta_unit'] or ' pts', e['prev_period']),
                                  'action': 'Open', 'href': e['href']})
            if e.get('near'):
                attention.append({'tone': 'mid', 'icon': 'fa-bullseye',
                                  'text': '%d %s one credit short of 5 credits in %s %s — the easiest wins.' % (
                                      e['near'], 'student is' if e['near'] == 1 else 'students are',
                                      e['name'], e['period']),
                                  'action': 'See who', 'href': e.get('analytics') or e['href']})
            if e.get('low'):
                attention.append({'tone': 'bad', 'icon': 'fa-triangle-exclamation',
                                  'text': '%d scored below 160 in %s %s — under most institutions\' minimum.' % (
                                      e['low'], e['name'], e['period']),
                                  'action': 'Open', 'href': e['href']})
    order = {'bad': 0, 'mid': 1, 'good': 2}
    attention.sort(key=lambda a: order.get(a['tone'], 3))
    live = [e for lv in levels for e in lv['exams'] if not e.get('empty')]
    totals = {'exams': len(live), 'candidates': sum(int(e['facts'][0][1] or 0) for e in live),
              'levels': sum(1 for lv in levels if any(not e.get('empty') for e in lv['exams']))}
    return {'levels': levels, 'attention': attention[:6], 'totals': totals}


def _num(v, unit):
    return ('%s%%' % v) if unit == '%' else ('%s%s' % (v, unit))


def _has_endpoint(name):
    from flask import current_app
    return name in current_app.view_functions
