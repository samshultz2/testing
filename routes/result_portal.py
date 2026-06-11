"""Scratch-card admin + public result-checker portal.

* scratchcards_bp (/scratch-cards): staff generate/print/track result cards.
* result_portal_bp (/check-result): public page where a student/parent enters
  Student ID + card PIN to view a published term result. No staff login.
"""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash)

from models import db, ScratchCard, ResultCheckLog, Term, Student
from utils.access_control import login_required, result_card_required
from utils.audit import log_action
from utils.report_card import build_report_card

scratchcards_bp = Blueprint('scratchcards', __name__, url_prefix='/scratch-cards')
result_portal_bp = Blueprint('result_portal', __name__, url_prefix='/check-result')


# ===========================================================================
# ADMIN
# ===========================================================================

@scratchcards_bp.route('/')
@login_required
def index():
    batch = request.args.get('batch') or None
    q = ScratchCard.query
    if batch:
        q = q.filter_by(batch_label=batch)
    cards = q.order_by(ScratchCard.created_at.desc(), ScratchCard.id.desc()).all()
    batches = [b[0] for b in db.session.query(ScratchCard.batch_label)
               .distinct().all() if b[0]]
    stats = {
        'total': ScratchCard.query.count(),
        'active': ScratchCard.query.filter_by(is_active=True).count(),
        'used': sum(c.used_count or 0 for c in ScratchCard.query.all()),
    }
    return render_template('scratchcards/index.html', cards=cards, batches=batches,
                           batch=batch, stats=stats,
                           terms=Term.query.order_by(Term.id.desc()).all())


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
    flash(f'Generated {count} scratch card(s).', 'success')
    ids = ','.join(str(c.id) for c in created)
    return redirect(url_for('scratchcards.print_cards', ids=ids))


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
    flash(f'Card {card.serial} {"activated" if card.is_active else "disabled"}.',
          'success')
    return redirect(url_for('scratchcards.index', batch=card.batch_label))


@scratchcards_bp.route('/publish/<int:term_id>', methods=['POST'])
@login_required
@result_card_required
def publish(term_id):
    term = db.get_or_404(Term, term_id)
    term.results_published = not term.results_published
    db.session.commit()
    state = 'released' if term.results_published else 'hidden'
    log_action('results.publish', f'{term.full_name}: {state}')
    flash(f'Results for {term.full_name} are now {state}.', 'success')
    # Optionally notify parents (uses the existing bulk-SMS compose flow).
    if term.results_published and request.form.get('notify') == 'on':
        flash('Send this SMS to notify parents that results are released.', 'info')
        return redirect(url_for('comms.compose', audience='all', notice='results'))
    nxt = request.form.get('next')
    if nxt and nxt.startswith('/') and not nxt.startswith('//'):
        return redirect(nxt)
    return redirect(url_for('scratchcards.index'))


@scratchcards_bp.route('/logs')
@login_required
def logs():
    rows = (ResultCheckLog.query.order_by(ResultCheckLog.checked_at.desc())
            .limit(500).all())
    return render_template('scratchcards/logs.html', rows=rows)


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
        student_id = (request.form.get('student_id') or '').strip()
        pin = (request.form.get('pin') or '').strip()
        term_id = request.form.get('term_id', type=int)

        student = Student.query.filter_by(student_id=student_id).first()
        card = ScratchCard.query.filter_by(pin=pin).first()

        if not student:
            _log_check(card, None, None, False, f'unknown student id {student_id}')
            flash('Student ID not found.', 'error')
            return render_template('scratchcards/check.html', **ctx)
        if not card:
            _log_check(None, student, None, False, 'invalid pin')
            flash('Invalid card PIN.', 'error')
            return render_template('scratchcards/check.html', **ctx)
        if not card.can_use():
            _log_check(card, student, None, False, 'card exhausted/disabled')
            flash('This card has no checks left or has been disabled.', 'error')
            return render_template('scratchcards/check.html', **ctx)
        if card.student_id and card.student_id != student.id:
            _log_check(card, student, None, False, 'card bound to another student')
            flash('This card is not valid for that Student ID.', 'error')
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

        # Consume a use only on a successful lookup.
        card.used_count = (card.used_count or 0) + 1
        _log_check(card, student, term, True, f'viewed; {card.uses_left} left')

        return render_template('scratchcards/result.html', student=student,
                               term=term, report_data=report_data,
                               uses_left=card.uses_left)

    return render_template('scratchcards/check.html', **ctx)
