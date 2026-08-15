"""Published, PII-safe data for the public Website Builder.

This is the ONLY bridge between the private SIS and the public internet, so it is
deliberately narrow: it exposes school branding, non-personal aggregate stats,
and upcoming *all-audience* calendar events — never a student, parent, or staff
record, and never a query that isn't already filtered to public content. Every
data-backed block reads through here so a mistake can only happen in one place.
"""
from datetime import date
from utils import timeutil


def public_branding():
    """School identity for the public site — the same single source used by the
    portal header and every printout (utils.school.school_profile)."""
    from utils.school import school_profile
    from models.models import SchoolSettings
    p = school_profile()
    return {
        'name': p['name'] or 'Our School',
        'motto': p['motto'] or '',
        'address': p['address'] or '',
        'phone': p['phone'] or '',
        'email': p['email'] or '',
        'logo_url': p['logo_url'] or '',
        'established': SchoolSettings.get('school_established', '') or '',
    }


def public_events(limit=6):
    """Upcoming, all-audience calendar events — the public subset of the school
    calendar (term dates, holidays, sports days…). Staff/Students/Parents-only
    events are never exposed. Only non-personal fields are returned."""
    from models import SchoolEvent
    try:
        rows = (SchoolEvent.query
                .filter(SchoolEvent.audience == 'All')
                .filter(db.func.coalesce(SchoolEvent.end_date, SchoolEvent.start_date) >= timeutil.today())
                .order_by(SchoolEvent.start_date.asc())
                .limit(max(1, min(limit, 24))).all())
    except Exception:
        return []
    return [{
        'title': e.title, 'category': e.category, 'color': e.color,
        'start': e.start_date, 'end': e.end_date, 'location': e.location or '',
        'description': (e.description or '')[:280],
    } for e in rows]


def public_stats():
    """Non-personal aggregate counts for a Statistics section — never a name or
    record, just totals a school is happy to advertise."""
    from models import Student, StaffMember, SchoolClass
    def _count(model, **f):
        try:
            return model.query.filter_by(**f).count()
        except Exception:
            return 0
    return {
        'students': _count(Student, is_active=True),
        'staff': _count(StaffMember, is_active=True),
        'classes': _count(SchoolClass),
    }


def public_assignments():
    """Published holiday-assignment documents grouped by class, newest first.
    Non-personal: just class labels, titles and download links — no student data."""
    from models import HolidayAssignment
    from flask import url_for
    try:
        rows = (HolidayAssignment.query.filter_by(is_published=True)
                .order_by(HolidayAssignment.class_label.asc(),
                          HolidayAssignment.created_at.desc()).all())
    except Exception:
        return []
    groups, order = {}, []
    for r in rows:
        if r.class_label not in groups:
            groups[r.class_label] = []
            order.append(r.class_label)
        groups[r.class_label].append({
            'id': r.id, 'title': r.title, 'ext': r.ext, 'icon': r.icon,
            'size': r.size_human, 'session': r.session_label or '',
            'url': url_for('website.assignment_download', aid=r.id),
        })
    return [{'class_label': k, 'items': groups[k]} for k in order]


def public_posts(limit=6):
    """Published news/blog posts, newest first, for a blog listing block. Only
    non-personal fields; author is a name the admin chose to show."""
    from models import NewsPost
    from flask import url_for
    try:
        rows = (NewsPost.query.filter_by(is_published=True)
                .order_by(NewsPost.published_at.desc(), NewsPost.id.desc())
                .limit(max(1, min(limit, 24))).all())
    except Exception:
        return []
    return [{
        'title': p.title, 'slug': p.slug, 'excerpt': p.excerpt or '',
        'cover': p.cover_image or '', 'category': p.category or '',
        'author': p.author or '', 'date': p.published_at,
        'url': url_for('website.news_article', slug=p.slug),
    } for p in rows]


def public_context():
    """The bundle passed to the public renderer. Cached per-request via flask.g."""
    from flask import g, has_request_context
    if has_request_context() and hasattr(g, '_wb_ctx'):
        return g._wb_ctx
    ctx = {'branding': public_branding(), 'events': public_events(),
           'stats': public_stats(), 'assignments': public_assignments(),
           'posts': public_posts()}
    if has_request_context():
        g._wb_ctx = ctx
    return ctx


# db handle used by public_events' func.coalesce
from models.models import db  # noqa: E402
