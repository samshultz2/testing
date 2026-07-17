"""Term-end board-pack delivery.

Emails the institution analytics board pack (PDF) to the school's owners /
administrators. Two entry points:

* ``deliver_board_pack`` — build & send now (used by the manual "Email to
  owners" button and by the scheduler).
* ``run_board_pack_delivery_if_due`` — the once-per-term scheduler hook: when
  the opt-in ``auto_board_pack`` setting is on, any term whose results have been
  published and that hasn't been delivered yet is sent automatically.
"""
import os
import re
import tempfile


def board_pack_recipients():
    """Owner / admin email addresses (active super_admin & admin users) plus any
    extra addresses configured in the ``board_pack_recipients`` setting."""
    from models import User, SchoolSettings
    emails = []
    for u in User.query.filter(User.is_active == True,  # noqa: E712
                               User.role.in_(('super_admin', 'admin'))).all():
        if u.email:
            emails.append(u.email.strip())
    extra = SchoolSettings.get('board_pack_recipients') or ''
    for e in re.split(r'[,;\s]+', extra):
        if e.strip():
            emails.append(e.strip())
    return list(dict.fromkeys(e for e in emails if e))     # de-dup, keep order


def deliver_board_pack(term_id=None, scope='school', scope_id=None, force=False):
    """Build the board pack for a term/scope and email it to the owners.

    Returns a dict describing the outcome. ``force`` skips the once-per-term
    guard (used by the manual button). Assumes an app context is active.
    """
    from models import db, Term, SchoolSettings
    from utils.results_analytics_org import org_analytics
    from utils.analytics_org_pdf import institution_pdf, institution_filename
    from utils.numfmt import fmt_num as _n
    from utils import mailer

    if term_id is None:
        term = (Term.query.filter_by(results_published=True).order_by(Term.id.desc()).first())
        if not term:
            from utils.helpers import get_active_term
            term = get_active_term()
        term_id = term.id if term else None
    if not term_id:
        return {'sent': 0, 'reason': 'no term'}

    marker = f'board_pack_sent:{term_id}'
    if not force and SchoolSettings.get(marker):
        return {'sent': 0, 'reason': 'already sent', 'term_id': term_id}

    data = org_analytics(term_id, scope, scope_id, None, use_cache=False)
    if not (data.get('summary') or {}).get('assessed'):
        return {'sent': 0, 'reason': 'no scores', 'term_id': term_id}
    if not mailer.is_configured():
        return {'sent': 0, 'reason': 'email not configured', 'term_id': term_id}
    recipients = board_pack_recipients()
    if not recipients:
        return {'sent': 0, 'reason': 'no recipients', 'term_id': term_id}

    term = db.session.get(Term, term_id)
    try:
        from utils.school import school_profile
        school = school_profile().get('name') or 'School'
    except Exception:
        school = 'School'
    s = data.get('summary') or {}
    pdf = institution_pdf(data, term)

    subject = f"Academic Board Pack — {data.get('scope_label', 'Whole School')} — {term.full_name if term else ''}"
    lines = [
        f"{school} — academic performance for {term.full_name if term else ''}.",
        '',
        f"Scope: {data.get('scope_label', 'Whole School')}",
        f"Students assessed: {s.get('assessed')}/{s.get('students')}",
        f"Average score: {_n(s.get('class_average'))}",
        f"Pass rate: {_n(s.get('pass_rate'))}%   Distinctions: {_n(s.get('distinction_rate'))}%",
        f"Entry completion: {_n(s.get('completion'))}%",
        '',
        'The full board pack (leagues, teacher effectiveness, attendance and '
        'recommendations) is attached as a PDF.',
    ]
    body = '\n'.join(lines)
    html = None
    try:
        html = mailer.branded_html(
            f"Academic Board Pack · {term.full_name if term else ''}",
            [f"Scope: <b>{data.get('scope_label', 'Whole School')}</b>",
             f"Average <b>{_n(s.get('class_average'))}</b> · Pass rate "
             f"<b>{_n(s.get('pass_rate'))}%</b> · Distinctions <b>{_n(s.get('distinction_rate'))}%</b>",
             f"{s.get('assessed')}/{s.get('students')} students assessed · "
             f"{_n(s.get('completion'))}% entry completion",
             "The full board pack is attached as a PDF."])
    except Exception:
        html = None

    fd, path = tempfile.mkstemp(suffix='.pdf')
    try:
        os.write(fd, pdf)
        os.close(fd)
        ok = mailer.send_email(
            recipients, subject, body, html=html,
            attachments=[(path, institution_filename(data, term, 'pdf'), 'application/pdf')])
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    if ok and not force:
        SchoolSettings.set(marker, term.full_name if term else str(term_id), 'string',
                           'Board pack already emailed for this term (auto-delivery guard)')
    return {'sent': len(recipients) if ok else 0, 'ok': bool(ok), 'term_id': term_id,
            'recipients': recipients, 'reason': 'sent' if ok else 'send failed'}


def run_board_pack_delivery_if_due(app):
    """Scheduler hook: when auto-delivery is enabled, email the board pack once
    for every published-but-not-yet-delivered term. No-op unless opted in."""
    from models import Term, SchoolSettings
    with app.app_context():
        if not SchoolSettings.get('auto_board_pack'):
            return
        for term in Term.query.filter_by(results_published=True).all():
            if SchoolSettings.get(f'board_pack_sent:{term.id}'):
                continue
            try:
                deliver_board_pack(term_id=term.id)
            except Exception:
                app.logger.exception('board pack delivery failed for term %s', term.id)
