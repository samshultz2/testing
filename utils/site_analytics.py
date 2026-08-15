"""First-party, privacy-friendly analytics for a school's public website.

Deliberately minimal and self-hosted: page views are counted server-side into
per-day aggregate rows in the school's own tenant DB. No cookies are set, no
third-party tracker is loaded, and no raw IP address is ever stored — unique
visitors are counted via a per-day, salted, non-reversible hash that cannot be
turned back into a person. Recording is best-effort: a failure here must never
break the public page, so every write swallows its own errors.
"""
import hashlib
from utils import timeutil
from datetime import date, timedelta

from flask import current_app

from models import db, SiteViewDaily, SiteReferrerDaily, SiteVisitorDaily

# Substrings that mark an automated client; these aren't real visits.
_BOT_UA = ('bot', 'crawl', 'spider', 'slurp', 'bingpreview', 'facebookexternalhit',
           'whatsapp', 'telegrambot', 'headlesschrome', 'python-requests',
           'curl/', 'wget/', 'httpx', 'monitor', 'pingdom', 'uptimerobot')


def _is_bot(ua):
    ua = (ua or '').lower()
    return any(tok in ua for tok in _BOT_UA)


def _client_ip(req):
    fwd = req.headers.get('X-Forwarded-For', '')
    return (fwd.split(',')[0].strip() if fwd else (req.remote_addr or '')).strip()


def _visitor_hash(day, req):
    """Per-day, salted digest of IP+UA. Rotates daily and can't be reversed to
    identify anyone — it exists only to de-duplicate a visitor within one day."""
    secret = current_app.config.get('SECRET_KEY', '') or 'site-analytics'
    raw = f'{day.isoformat()}|{secret}|{_client_ip(req)}|{req.headers.get("User-Agent", "")}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _referrer_source(req):
    ref = req.headers.get('Referer') or req.headers.get('Referrer') or ''
    if not ref:
        return 'direct'
    try:
        from urllib.parse import urlparse
        host = (urlparse(ref).hostname or '').lower()
    except Exception:
        return 'direct'
    if not host:
        return 'direct'
    # Treat our own host as direct (internal navigation isn't a referral).
    if host == (req.host or '').split(':')[0].lower():
        return 'direct'
    if host.startswith('www.'):
        host = host[4:]
    return host[:120]


def _bump(model, commit_kwargs):
    """Increment a (day, key) aggregate row's view count, creating it if new."""
    row = model.query.filter_by(**{k: v for k, v in commit_kwargs.items()}).first()
    if row is None:
        db.session.add(model(views=1, **commit_kwargs))
    else:
        row.views = (row.views or 0) + 1
    db.session.commit()


def record(path, req):
    """Count one public page view. Best-effort and side-effect-free on failure."""
    if _is_bot(req.headers.get('User-Agent')):
        return
    day = timeutil.today()
    path = (path or '/')[:200]
    try:
        _bump(SiteViewDaily, {'day': day, 'path': path})
    except Exception:
        db.session.rollback()
    try:
        _bump(SiteReferrerDaily, {'day': day, 'source': _referrer_source(req)})
    except Exception:
        db.session.rollback()
    # Unique visitor: first hit today for this hash inserts a row; repeats collide
    # on the unique constraint and are quietly ignored.
    try:
        db.session.add(SiteVisitorDaily(day=day, visitor_hash=_visitor_hash(day, req)))
        db.session.commit()
    except Exception:
        db.session.rollback()


def summary(days=30):
    """Aggregate stats for the admin dashboard over the last ``days`` days."""
    from sqlalchemy import func
    today = timeutil.today()
    start = today - timedelta(days=days - 1)

    views_rows = (db.session.query(SiteViewDaily.day, func.sum(SiteViewDaily.views))
                  .filter(SiteViewDaily.day >= start)
                  .group_by(SiteViewDaily.day).all())
    by_day = {d: int(v or 0) for d, v in views_rows}
    series = [{'day': (start + timedelta(days=i)),
               'views': by_day.get(start + timedelta(days=i), 0)}
              for i in range(days)]

    total_views = sum(p['views'] for p in series)
    unique_visitors = (db.session.query(func.count(SiteVisitorDaily.id))
                       .filter(SiteVisitorDaily.day >= start).scalar() or 0)

    top_pages = (db.session.query(SiteViewDaily.path, func.sum(SiteViewDaily.views).label('v'))
                 .filter(SiteViewDaily.day >= start)
                 .group_by(SiteViewDaily.path).order_by(func.sum(SiteViewDaily.views).desc())
                 .limit(10).all())
    top_referrers = (db.session.query(SiteReferrerDaily.source, func.sum(SiteReferrerDaily.views).label('v'))
                     .filter(SiteReferrerDaily.day >= start)
                     .group_by(SiteReferrerDaily.source).order_by(func.sum(SiteReferrerDaily.views).desc())
                     .limit(10).all())
    return {
        'days': days, 'start': start, 'end': today,
        'total_views': total_views, 'unique_visitors': int(unique_visitors),
        'series': series,
        'top_pages': [{'path': p, 'views': int(v)} for p, v in top_pages],
        'top_referrers': [{'source': s, 'views': int(v)} for s, v in top_referrers],
    }
