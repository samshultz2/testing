"""Scheduled fee-reminder job.

Opt-in via ``FEE_REMINDER_ENABLED``. When enabled, a background job prepares a
*Draft* SMS campaign to fee defaulters for the active term and bells admins to
review and send it. Nothing is sent automatically — the human send-gate is kept,
which matters because this messages parents about money.

Idempotent and safe to call repeatedly: a new draft is prepared at most once per
``FEE_REMINDER_INTERVAL_DAYS`` (guarded by a DB check), so schedulers can call it
on every poll without piling up drafts. ``dry_run=True`` reports the counts it
would act on without creating anything; ``force=True`` bypasses both the opt-in
gate and the interval guard (for manual/testing use).
"""
import logging
from datetime import datetime, timedelta

_log = logging.getLogger('posyhub.reminders')

_DEFAULT_BODY = (
    'Dear {parent}, a fee balance of {balance} is outstanding for {student} '
    '({term}). Kindly arrange payment. Thank you. - {school}'
)


def _reminder_body():
    from models import MessageTemplate
    t = MessageTemplate.query.filter(MessageTemplate.name.ilike('%fee%reminder%'),
                                     MessageTemplate.is_active == True).first()
    return t.body if t else _DEFAULT_BODY


def run_fee_reminders(app, *, dry_run=False, force=False):
    """Prepare a Draft fee-reminder campaign. Returns a status dict."""
    from config import Config
    enabled = bool(getattr(Config, 'FEE_REMINDER_ENABLED', False))
    if not (enabled or force or dry_run):
        return {'status': 'disabled'}
    interval = int(getattr(Config, 'FEE_REMINDER_INTERVAL_DAYS', 7) or 7)

    # A request context with central scope so the job sees every branch's
    # defaulters and audience resolution (which reads the session) works.
    with app.test_request_context('/'):
        from flask import session, url_for
        session['scope'] = 'central'
        session['role'] = 'super_admin'

        from utils.helpers import get_active_term
        term = get_active_term()
        if term is None:
            return {'status': 'no-active-term'}

        from models import Message
        from utils import comms

        if not force:
            since = datetime.now() - timedelta(days=interval)
            recent = (Message.query
                      .filter(Message.title.ilike('Fee reminder:%'),
                              Message.term_id == term.id,
                              Message.created_at >= since).first())
            if recent:
                return {'status': 'recent-exists', 'message_id': recent.id}

        targets = comms.resolve_audience('defaulters', term)
        reachable = [t for t in targets if t['phone']]
        if dry_run:
            return {'status': 'dry-run', 'term': term.full_name,
                    'defaulters': len(targets), 'reachable': len(reachable)}
        if not reachable:
            return {'status': 'no-defaulters', 'term': term.full_name}

        msg = comms.create_draft_campaign(
            _reminder_body(), audience='defaulters', term=term,
            title=f'Fee reminder: {term.full_name}', created_by='auto-reminder')
        if msg is None:
            return {'status': 'no-defaulters', 'term': term.full_name}

        from utils.notify import notify_admins
        notify_admins(
            'Fee reminder ready',
            f'A draft SMS to {msg.recipient_count} fee defaulter(s) for '
            f'{term.full_name} is ready to review and send.',
            url=url_for('comms.message_detail', message_id=msg.id),
            category='finance')
        _log.info('Fee reminder draft #%s created for %s recipients',
                  msg.id, msg.recipient_count)
        return {'status': 'created', 'message_id': msg.id,
                'recipients': msg.recipient_count}
