"""Scratch-card admin + public result-checker portal.

* scratchcards_bp (/scratch-cards): staff generate/print/track result cards.
* result_portal_bp (/check-result): public page where a student/parent enters
  Student ID + card PIN to view a published term result. No staff login.
"""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify)

from models import db, ScratchCard, ResultCheckLog, Term, Student
from utils.access_control import login_required, result_card_required
from utils.security import login_limiter
from utils.audit import log_action
from utils.report_card import build_report_card
from utils.helpers import session_terms

scratchcards_bp = Blueprint('scratchcards', __name__, url_prefix='/scratch-cards')
result_portal_bp = Blueprint('result_portal', __name__, url_prefix='/check-result')


# --- SPA helpers (no-reload React shell + JSON-aware action responses) ---
from utils.spa import section_responders
_wants_json, _render, _ok, _err = section_responders(
    'scratchcards/app.html', 'sc_json', 'scratchcards.index')


# ===========================================================================
# ADMIN
# ===========================================================================

def _apply_card_status(q, status):
    """Narrow a ScratchCard query by a status keyword used across the list and
    the rule-based bulk actions."""
    if status == 'active':
        return q.filter(ScratchCard.is_active.is_(True))
    if status == 'disabled':
        return q.filter(ScratchCard.is_active.is_(False))
    if status == 'unused':
        return q.filter((ScratchCard.used_count == 0) | (ScratchCard.used_count.is_(None)))
    if status == 'used':
        return q.filter(ScratchCard.used_count > 0)
    return q


def _id_list(raw):
    out = []
    for tok in (raw or '').replace(',', ' ').split():
        try:
            out.append(int(tok))
        except ValueError:
            pass
    return out


@scratchcards_bp.route('/')
@login_required
def index():
    batch = request.args.get('batch') or None
    status = request.args.get('status') or None
    page = max(1, request.args.get('page', 1, type=int) or 1)
    per_page = min(max(request.args.get('per_page', 50, type=int) or 50, 10), 200)

    q = ScratchCard.query
    if batch:
        q = q.filter_by(batch_label=batch)
    q = _apply_card_status(q, status)
    pg = (q.order_by(ScratchCard.created_at.desc(), ScratchCard.id.desc())
          .paginate(page=page, per_page=per_page, error_out=False))

    batches = [b[0] for b in db.session.query(ScratchCard.batch_label)
               .distinct().all() if b[0]]
    from sqlalchemy import func
    stats = {
        'total': ScratchCard.query.count(),
        'active': ScratchCard.query.filter_by(is_active=True).count(),
        'used': db.session.query(func.coalesce(func.sum(ScratchCard.used_count), 0)).scalar() or 0,
    }
    terms = session_terms()
    return _render({
        'page': 'index',
        'stats': stats,
        'batch': batch,
        'status': status or '',
        'batches': batches,
        # pagination + filtered-count meta for the list controls
        'pg': {'page': pg.page, 'pages': pg.pages, 'total': pg.total,
               'per_page': per_page, 'has_prev': pg.has_prev, 'has_next': pg.has_next},
        'terms': [{'id': t.id, 'name': t.full_name or t.name,
                   'results_published': bool(t.results_published),
                   'publish_url': url_for('scratchcards.publish', term_id=t.id)} for t in terms],
        'cards': [{'id': c.id, 'serial': c.serial, 'pin': c.pin,
                   'used_count': c.used_count, 'max_uses': c.max_uses, 'uses_left': c.uses_left,
                   'term_name': c.term.name if c.term else 'Any', 'batch_label': c.batch_label or '—',
                   'is_active': bool(c.is_active),
                   'toggle_url': url_for('scratchcards.toggle', card_id=c.id)} for c in pg.items],
        'generate_url': url_for('scratchcards.generate'),
        'logs_url': url_for('scratchcards.logs'),
        'self_url': url_for('scratchcards.index'),
        'bulk_toggle_url': url_for('scratchcards.bulk_toggle'),
        'bulk_delete_url': url_for('scratchcards.bulk_delete'),
        'print_batch_url': url_for('scratchcards.print_cards', batch=batch) if batch else None,
    })


@scratchcards_bp.route('/bulk-toggle', methods=['POST'])
@login_required
def bulk_toggle():
    """Enable or disable many cards at once (selected ids)."""
    ids = _id_list(request.form.get('ids'))
    if not ids:
        return _err('No cards selected.', url_for('scratchcards.index'))
    active = request.form.get('active') == '1'
    n = (ScratchCard.query.filter(ScratchCard.id.in_(ids))
         .update({'is_active': active}, synchronize_session=False))
    db.session.commit()
    log_action('scratchcard.bulk_toggle', f'{n} card(s) → {"active" if active else "disabled"}')
    return _ok(f'{n} card(s) {"enabled" if active else "disabled"}.', url_for('scratchcards.index'))


@scratchcards_bp.route('/bulk-delete', methods=['POST'])
@login_required
def bulk_delete():
    """Delete cards — either an explicit selection (``ids``) or, when none is
    given, everything matching a rule (batch + status) up to an optional
    ``limit`` (e.g. 200), oldest first. Audit logs are kept (their card link is
    cleared) so a delete never loses the check history."""
    ids = _id_list(request.form.get('ids'))
    if ids:
        target_ids = [r.id for r in ScratchCard.query
                      .filter(ScratchCard.id.in_(ids)).with_entities(ScratchCard.id).all()]
    else:
        batch = request.form.get('batch') or None
        status = request.form.get('status') or None
        try:
            limit = int(request.form.get('limit') or 0)
        except (TypeError, ValueError):
            limit = 0
        q = ScratchCard.query
        if batch:
            q = q.filter_by(batch_label=batch)
        q = _apply_card_status(q, status)
        q = q.order_by(ScratchCard.created_at.asc(), ScratchCard.id.asc())
        if limit > 0:
            q = q.limit(limit)
        target_ids = [r.id for r in q.with_entities(ScratchCard.id).all()]

    if not target_ids:
        return _err('No matching cards to delete.', url_for('scratchcards.index'))
    ResultCheckLog.query.filter(ResultCheckLog.card_id.in_(target_ids)).update(
        {'card_id': None}, synchronize_session=False)
    n = ScratchCard.query.filter(ScratchCard.id.in_(target_ids)).delete(synchronize_session=False)
    db.session.commit()
    log_action('scratchcard.bulk_delete', f'{n} card(s) deleted')
    return _ok(f'Deleted {n} scratch card(s).', url_for('scratchcards.index'))


@scratchcards_bp.route('/generate', methods=['POST'])
@login_required
@result_card_required
def generate():
    try:
        count = max(1, min(int(request.form.get('count', 10)), 500))
    except (ValueError, TypeError):
        count = 10
    try:
        max_uses = max(1, min(int(request.form.get('max_uses', 5)), 100))
    except (ValueError, TypeError):
        max_uses = 5
    term_id = request.form.get('term_id', type=int)
    label = (request.form.get('batch_label') or '').strip() or None

    created = []
    for _ in range(count):
        card = ScratchCard.generate_unique(max_uses=max_uses, term_id=term_id,
                                           batch_label=label)
        db.session.add(card)
        created.append(card)
    db.session.commit()
    log_action('scratchcard.generate',
               f'{count} card(s), {max_uses} uses each'
               + (f', term_id={term_id}' if term_id else '')
               + (f', batch="{label}"' if label else ''))
    ids = ','.join(str(c.id) for c in created)
    return _ok(f'Generated {count} scratch card(s).',
               url_for('scratchcards.print_cards', ids=ids))


@scratchcards_bp.route('/print')
@login_required
def print_cards():
    ids = (request.args.get('ids') or '').strip()
    if ids:
        id_list = [int(x) for x in ids.split(',') if x.strip().isdigit()]
        cards = ScratchCard.query.filter(ScratchCard.id.in_(id_list)).all()
    else:
        batch = request.args.get('batch')
        cards = (ScratchCard.query.filter_by(batch_label=batch).all()
                 if batch else [])
    portal_url = url_for('result_portal.check', _external=True)
    return render_template('scratchcards/print.html', cards=cards,
                           portal_url=portal_url)


@scratchcards_bp.route('/<int:card_id>/toggle', methods=['POST'])
@login_required
def toggle(card_id):
    card = db.get_or_404(ScratchCard, card_id)
    card.is_active = not card.is_active
    db.session.commit()
    return _ok(f'Card {card.serial} {"activated" if card.is_active else "disabled"}.',
               url_for('scratchcards.index', batch=card.batch_label))


@scratchcards_bp.route('/publish/<int:term_id>', methods=['POST'])
@login_required
@result_card_required
def publish(term_id):
    term = db.get_or_404(Term, term_id)
    term.results_published = not term.results_published
    db.session.commit()
    state = 'released' if term.results_published else 'hidden'
    log_action('results.publish', f'{term.full_name}: {state}')
    from utils.notify import notify_admins
    notify_admins(f'Results {state}: {term.full_name}',
                  f'Term results were {state} on the result portal.',
                  url=url_for('scratchcards.index'),
                  category='success' if term.results_published else 'info')
    # Optionally notify parents: queue a *Draft* SMS campaign for staff to review
    # and send (never auto-dispatched). Falls back to the compose page if there
    # are no reachable parents.
    from utils import automations
    if (term.results_published and request.form.get('notify') == 'on'
            and automations.is_enabled('results_published')):
        from flask import session
        from utils import comms
        from models import MessageTemplate
        tpl = MessageTemplate.query.filter(MessageTemplate.name.ilike('%result%'),
                                           MessageTemplate.is_active == True).first()
        body = tpl.body if tpl else (
            'Dear {parent}, {term} results for {student} have been released. '
            'Please check the result portal. - {school}')
        draft = comms.create_draft_campaign(
            body, audience='all', term=term,
            title=f'Results released: {term.full_name}',
            created_by=session.get('username') or 'system')
        if draft:
            flash(f'Results for {term.full_name} are now released.', 'success')
            flash('A draft SMS to parents is ready — review the recipients and send.', 'info')
            return redirect(url_for('comms.message_detail', message_id=draft.id))
        flash(f'Results for {term.full_name} are now {state}.', 'success')
        flash('Send this SMS to notify parents that results are released.', 'info')
        return redirect(url_for('comms.compose', audience='all', notice='results'))
    nxt = request.form.get('next')
    if nxt and nxt.startswith('/') and not nxt.startswith('//'):
        flash(f'Results for {term.full_name} are now {state}.', 'success')
        return redirect(nxt)
    return _ok(f'Results for {term.full_name} are now {state}.',
               url_for('scratchcards.index'))


@scratchcards_bp.route('/logs')
@login_required
def logs():
    rows = (ResultCheckLog.query.order_by(ResultCheckLog.checked_at.desc())
            .limit(500).all())
    return _render({
        'page': 'logs',
        'index_url': url_for('scratchcards.index'),
        'rows': [{'when': r.checked_at.strftime('%d %b %Y %H:%M') if r.checked_at else '',
                  'student': r.student.full_name if r.student else '—',
                  'term': r.term.name if r.term else '—',
                  'card': r.card.serial if r.card else '—',
                  'success': bool(r.success), 'detail': r.detail,
                  'ip': r.ip_address or ''} for r in rows],
    })


# ===========================================================================
# PUBLIC RESULT CHECKER
# ===========================================================================

def _log_check(card, student, term, success, detail):
    try:
        db.session.add(ResultCheckLog(
            card_id=card.id if card else None,
            student_id=student.id if student else None,
            term_id=term.id if term else None,
            success=success, detail=detail,
            ip_address=request.remote_addr,
            user_agent=(request.headers.get('User-Agent') or '')[:300]))
        db.session.commit()
    except Exception:
        db.session.rollback()


@result_portal_bp.route('/', methods=['GET', 'POST'])
def check():
    published_terms = (Term.query.filter_by(results_published=True)
                       .order_by(Term.id.desc()).all())
    ctx = {'published_terms': published_terms}

    if request.method == 'POST':
        # Throttle PIN/Student-ID guessing by client IP. A successful check
        # clears the counter, so genuine parents checking several children are
        # unaffected while brute-forcing is shut down.
        rkey = f"result_check:{request.remote_addr or 'unknown'}"
        if login_limiter.is_rate_limited(rkey, max_attempts=20, window_minutes=15):
            wait = login_limiter.get_remaining_time(rkey, 15) // 60 + 1
            flash(f'Too many attempts. Please try again in about {wait} minute(s).', 'error')
            return render_template('scratchcards/check.html', **ctx)
        login_limiter.record_attempt(rkey)

        student_id = (request.form.get('student_id') or '').strip()
        pin = (request.form.get('pin') or '').strip()
        term_id = request.form.get('term_id', type=int)

        student = Student.query.filter_by(student_id=student_id).first()
        card = ScratchCard.query.filter_by(pin=pin).first()

        # Anti-enumeration: a wrong Student ID, a wrong PIN, and a card bound to
        # someone else all return ONE generic message, so an attacker can't probe
        # which sequential Student IDs exist. The internal audit log stays specific.
        _BAD_CREDS = 'The Student ID or card PIN is incorrect.'
        if not student:
            _log_check(card, None, None, False, f'unknown student id {student_id}')
            flash(_BAD_CREDS, 'error')
            return render_template('scratchcards/check.html', **ctx)
        if not card:
            _log_check(None, student, None, False, 'invalid pin')
            flash(_BAD_CREDS, 'error')
            return render_template('scratchcards/check.html', **ctx)
        if not card.can_use():
            _log_check(card, student, None, False, 'card exhausted/disabled')
            flash('This card has no checks left or has been disabled.', 'error')
            return render_template('scratchcards/check.html', **ctx)
        if card.student_id and card.student_id != student.id:
            _log_check(card, student, None, False, 'card bound to another student')
            flash(_BAD_CREDS, 'error')
            return render_template('scratchcards/check.html', **ctx)

        # Resolve term: a card-bound term wins, else the chosen published term.
        term = None
        if card.term_id:
            term = db.session.get(Term, card.term_id)
        elif term_id:
            term = db.session.get(Term, term_id)
        if not term or not term.results_published:
            _log_check(card, student, term, False, 'term not published')
            flash('Please choose a term whose results have been released.', 'error')
            return render_template('scratchcards/check.html', **ctx)

        enrollment, report_data = build_report_card(student.id, term.id)
        if not report_data:
            _log_check(card, student, term, False, 'no result for term')
            flash('No result found for that student in the selected term.', 'error')
            return render_template('scratchcards/check.html', **ctx)

        # Consume a use only on a successful lookup, and bind the card to this
        # student on first use. After binding, the check at the top rejects any
        # other Student ID, so a valid PIN can no longer be used to walk the
        # (sequential, guessable) Student-ID range and read other students'
        # results. We deliberately do NOT clear the throttle on success, so
        # PIN/ID guessing stays rate-limited.
        card.used_count = (card.used_count or 0) + 1
        if card.student_id is None:
            card.student_id = student.id
        _log_check(card, student, term, True, f'viewed; {card.uses_left} left')

        return render_template('scratchcards/result.html', student=student,
                               term=term, report_data=report_data,
                               uses_left=card.uses_left)

    return render_template('scratchcards/check.html', **ctx)
