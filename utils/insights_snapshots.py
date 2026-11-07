"""Weekly at-risk snapshots (who moved into / out of risk since last week) and
frozen exam-year headline numbers (stable year-on-year comparisons)."""
from __future__ import annotations

import json
from datetime import timedelta

from models import db, Student
from models.models_insights import AtRiskSnapshot, ExamYearSnapshot, ensure_insights_schema

SEVERITY = {'NOT_READY': 0, 'AT_RISK': 1, 'CONDITIONAL': 2}


def week_start(d):
    return d - timedelta(days=d.weekday())


def _today():
    from utils import timeutil
    return timeutil.today()


def record_week(flags, today=None):
    """Store this week's at-risk list (replacing any earlier copy for the same
    week). ``flags`` = {student_id: {'status', 'blockers', 'class'}}."""
    ensure_insights_schema()
    ws = week_start(today or _today())
    AtRiskSnapshot.query.filter_by(week_start=ws).delete(synchronize_session=False)
    for sid, f in flags.items():
        db.session.add(AtRiskSnapshot(week_start=ws, student_id=sid, status=f.get('status'),
                                      blockers=json.dumps(f.get('blockers') or []),
                                      class_label=(f.get('class') or '')[:60]))
    db.session.commit()
    return ws


def current_flags(session_id=None, branch_id=None):
    from utils.at_risk_live import live_at_risk
    data = live_at_risk(session_id=session_id, branch_id=branch_id)
    out = {}
    for grp in data.get('by_class', []):
        for s in grp['students']:
            out[s['student_id']] = {'status': s['status'], 'blockers': s.get('blockers') or [],
                                    'class': grp['class'], 'name': s['name']}
    return out


def weekly_changes(session_id=None, branch_id=None, today=None):
    """{'week', 'previous_week', 'new', 'left', 'worse', 'better', 'still', 'total'}.
    Records this week's snapshot, then compares with the latest earlier week."""
    ensure_insights_schema()
    flags = current_flags(session_id, branch_id)
    ws = record_week(flags, today)
    prev_week = (db.session.query(db.func.max(AtRiskSnapshot.week_start))
                 .filter(AtRiskSnapshot.week_start < ws).scalar())
    prev = {}
    if prev_week:
        for r in AtRiskSnapshot.query.filter_by(week_start=prev_week).all():
            prev[r.student_id] = {'status': r.status, 'blockers': json.loads(r.blockers or '[]'),
                                  'class': r.class_label}
    names = {}
    gone = [sid for sid in prev if sid not in flags]
    if gone:
        names = {s.id: s.full_name for s in Student.query.filter(Student.id.in_(gone)).all()}

    def row(sid, f, before=None):
        return {'student_id': sid, 'name': f.get('name') or names.get(sid, ''), 'class': f.get('class'),
                'status': f.get('status'), 'was': (before or {}).get('status'),
                'blockers': f.get('blockers') or []}
    new, worse, better, still = [], [], [], []
    for sid, f in flags.items():
        if sid not in prev:
            new.append(row(sid, f))
            continue
        a, b = SEVERITY.get(f['status'], 9), SEVERITY.get(prev[sid]['status'], 9)
        (worse if a < b else better if a > b else still).append(row(sid, f, prev[sid]))
    left = [row(sid, dict(prev[sid], name=names.get(sid, '')), prev[sid]) for sid in gone]
    key = lambda r: (SEVERITY.get(r['status'], 9), r['name'])  # noqa: E731
    return {'week': ws, 'previous_week': prev_week, 'total': len(flags),
            'new': sorted(new, key=key), 'left': sorted(left, key=lambda r: r['name']),
            'worse': sorted(worse, key=key), 'better': sorted(better, key=key), 'still': len(still)}


# --------------------------------------------------------------------------- #
# Frozen exam years
# --------------------------------------------------------------------------- #
def frozen(year, branch_id=None):
    ensure_insights_schema()
    row = ExamYearSnapshot.query.filter_by(exam_year=year, branch_id=branch_id).first()
    if not row:
        return None
    data = json.loads(row.data)
    data['_frozen_at'] = row.frozen_at
    data['_frozen_by'] = row.frozen_by
    return data


def freeze(year, branch_id=None, by=''):
    """Store the year's headline numbers as they are now (re-freezing replaces)."""
    from routes.results import jamb_school_stats, waec_school_stats
    from utils import exam_compare
    ensure_insights_schema()
    metrics = exam_compare.headline_metrics(jamb_school_stats(year, branch_id), waec_school_stats(year, branch_id))
    if not metrics.get('has_data'):
        raise ValueError('No WAEC or JAMB results for %s to freeze.' % year)
    row = ExamYearSnapshot.query.filter_by(exam_year=year, branch_id=branch_id).first()
    if row is None:
        row = ExamYearSnapshot(exam_year=year, branch_id=branch_id, data='{}')
        db.session.add(row)
    from utils import timeutil
    row.data = json.dumps(metrics)
    row.frozen_at = timeutil.now()
    row.frozen_by = by or ''
    db.session.commit()
    return metrics


def unfreeze(year, branch_id=None):
    ensure_insights_schema()
    ExamYearSnapshot.query.filter_by(exam_year=year, branch_id=branch_id).delete(synchronize_session=False)
    db.session.commit()
