"""Background refresh of the external-exams analytics.

The analytics hub's per-student risk/prediction rows and the WAEC↔JAMB
correlation are only written when results change or when someone clicks
*Recompute*. On a cold cache the first hub load of the day then pays for the
whole computation. This module packages that work into one reusable routine so
both the manual *Recompute* button and a once-a-day background job call the same
code — and stamps ``exam_analytics_refreshed_at`` so the UI can show freshness.
"""
from __future__ import annotations

REFRESH_KEY = 'exam_analytics_refreshed_at'
_DAILY_MARKER = 'last_exam_analytics_refresh_date'


def _distinct_years(limit=5):
    from models import db, WAECResult
    ys = [y[0] for y in db.session.query(WAECResult.exam_year).distinct().all() if y[0]]
    return sorted(ys, reverse=True)[:limit]


def _warm_hub_caches(year, branch_ids):
    """Prime the cached school-stat wrappers for ``year`` across the given
    branches (plus all-branches) so the next hub load is warm, not cold.

    Imported lazily to avoid a route<->util import cycle; best-effort per branch.
    """
    from routes.results import (waec_school_stats, jamb_school_stats,
                                 waec_jamb_correlation, bust_school_stats)
    bust_school_stats()                       # drop stale rows before repriming
    for bid in [None, *branch_ids]:
        try:
            waec_school_stats(year, bid)
            jamb_school_stats(year, bid)
            waec_jamb_correlation(year, bid)
        except Exception:
            from models import db
            db.session.rollback()


def run_exam_analytics_refresh(app=None, *, warm=True, branch_id=None):
    """Recompute the SSS3 cohort's risk/prediction rows, backfill recent-year
    WAEC↔JAMB correlation, optionally warm the hub caches, and stamp the refresh
    time. Returns a summary dict. Safe to call from a request or a background
    tick (no request-only state).
    """
    from flask import has_request_context
    from models import db, local_now
    from models.models import SchoolSettings
    from utils.analytics_engine import AnalyticsEngine

    # In a request (the manual Recompute button) scope to the SSS3 cohort in
    # view; in the background tick there is no session, so recompute everyone —
    # the at-risk register filters to SSS3 regardless.
    if has_request_context():
        from utils.helpers import get_sss3_students
        student_ids = [s.id for s in get_sss3_students()]
    else:
        student_ids = None
    n = AnalyticsEngine.recompute_all_students(student_ids=student_ids)

    years = _distinct_years()
    for yr in years:
        try:
            AnalyticsEngine.recompute_correlation(yr, branch_id=branch_id)
        except Exception:
            db.session.rollback()

    if warm and years:
        from models.models_branch import Branch
        branch_ids = [b.id for b in Branch.query.filter_by(is_active=True).all()]
        _warm_hub_caches(years[0], branch_ids)

    stamp = local_now().isoformat(timespec='seconds')
    SchoolSettings.set(REFRESH_KEY, stamp, 'string',
                       'Last time exam analytics were refreshed (auto or manual)')
    return {'students': n, 'years': years, 'at': stamp}


def refreshed_at():
    """The stored last-refresh timestamp (ISO string) or None."""
    from models.models import SchoolSettings
    return SchoolSettings.get(REFRESH_KEY)


def run_daily_refresh_if_due(app):
    """Once-a-day guard for the scheduled tick: refresh the exam analytics if the
    day's run hasn't happened yet. Mirrors the other daily jobs' DB-marker idiom
    so it fires once per day across all workers. Best-effort."""
    import time as _t
    from models.models import SchoolSettings
    today = _t.strftime('%Y-%m-%d')
    if SchoolSettings.get(_DAILY_MARKER) == today:
        return False
    try:
        run_exam_analytics_refresh(app, warm=True)
    except Exception:
        from models import db
        db.session.rollback()
        if app is not None:
            app.logger.exception('exam analytics refresh job failed')
        return False
    SchoolSettings.set(_DAILY_MARKER, today, 'string',
                       'Last date the daily exam-analytics refresh job ran')
    return True
