"""
Academic management routes - Sessions, Terms, Classes, Arms
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from utils import timeutil
from utils.helpers import get_active_term
from datetime import timedelta, date
from models import (
    db, AcademicSession, Term, SchoolClass, ClassArm, 
    ClassArmAssignment, StudentEnrollment, Week, Holiday, Student
)
from utils.helpers import login_required, parse_date, get_weeks_in_range

academics_bp = Blueprint('academics', __name__, url_prefix='/academics')

FMT = '%d %b %Y'


def _fd(d):
    return d.strftime(FMT) if d else None


# --- SPA helpers (no-reload React shell + JSON-aware action responses) -------
from utils.spa import section_responders
_wants_json, _render, _ok, _err = section_responders(
    'academics/app.html', 'acad_json', 'academics.sessions_list')


# ============================================================================
# ACADEMIC SESSIONS
# ============================================================================

def _next_session_name(name):
    """'2025/2026' → '2026/2027' (None when the name isn't year/year)."""
    import re
    m = re.match(r'^\s*(\d{4})\s*([/-])\s*(\d{4})\s*$', name or '')
    if not m:
        return None
    return f'{int(m.group(1)) + 1}{m.group(2)}{int(m.group(3)) + 1}'


def _shift_year(d):
    # 52 weeks keeps the weekday, so Monday starts stay Mondays.
    return d + timedelta(weeks=52) if d else None


@academics_bp.route('/sessions')
@login_required
def sessions_list():
    """Sessions as a year timeline: the current session's progress and terms,
    a one-tap "start next session" (with its three terms), and every session's
    terms, classes and students."""
    from sqlalchemy import func
    from utils.access_control import can_access_module
    sessions = AcademicSession.query.order_by(AcademicSession.name.desc()).all()
    today = date.today()
    terms = Term.query.all()
    by_sess = {}
    for t in terms:
        by_sess.setdefault(t.session_id, []).append(t)
    pupils = dict(db.session.query(Term.session_id, func.count(func.distinct(StudentEnrollment.student_id)))
                  .join(ClassArmAssignment, ClassArmAssignment.term_id == Term.id)
                  .join(StudentEnrollment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
                  .group_by(Term.session_id).all())
    classes = dict(db.session.query(Term.session_id, func.count(func.distinct(ClassArmAssignment.class_id)))
                   .join(ClassArmAssignment, ClassArmAssignment.term_id == Term.id)
                   .group_by(Term.session_id).all())

    def span(s):
        ts = by_sess.get(s.id, [])
        st = s.start_date or min((t.start_date for t in ts if t.start_date), default=None)
        en = s.end_date or max((t.end_date for t in ts if t.end_date), default=None)
        return st, en

    def term_state(t):
        if not (t.start_date and t.end_date):
            return 'nodates'
        return 'upcoming' if today < t.start_date else ('ended' if today > t.end_date else 'running')

    def row(s):
        st, en = span(s)
        state, prog = 'nodates', None
        if st and en:
            if today < st:
                state = 'upcoming'
            elif today > en:
                state, prog = 'ended', 100
            else:
                state, prog = 'running', round((today - st).days / max(1, (en - st).days) * 100)
        ts = sorted(by_sess.get(s.id, []), key=lambda t: t.term_number)
        return {'id': s.id, 'name': s.name, 'is_active': bool(s.is_active),
                'start_date': _fd(st), 'end_date': _fd(en),
                'start_iso': s.start_date.isoformat() if s.start_date else '',
                'end_iso': s.end_date.isoformat() if s.end_date else '',
                'dates_from_terms': bool(st and not s.start_date),
                'state': state, 'progress': prog,
                'days_left': (en - today).days if en and state == 'running' else None,
                'terms': [{'number': t.term_number, 'name': t.name, 'is_active': bool(t.is_active),
                           'state': term_state(t), 'start_date': _fd(t.start_date), 'end_date': _fd(t.end_date)} for t in ts],
                'students': pupils.get(s.id, 0), 'classes': classes.get(s.id, 0),
                'edit_url': url_for('academics.edit_session', session_id=s.id),
                'activate_url': url_for('academics.activate_session', session_id=s.id)}

    rows = [row(s) for s in sessions]
    cur = next((r for r in rows if r['is_active']), None)
    names = {s.name for s in sessions}
    nxt_name = _next_session_name(cur['name']) if cur else None
    nxt = None
    if cur and nxt_name and nxt_name not in names:
        cs = next(s for s in sessions if s.id == cur['id'])
        have = {t.term_number: t for t in by_sess.get(cs.id, [])}
        st, en = span(cs)
        nxt = {'name': nxt_name,
               'start_date': _shift_year(st).isoformat() if st else '',
               'end_date': _shift_year(en).isoformat() if en else '',
               'terms': [{'number': n, 'name': nm,
                          'start_date': _fd(_shift_year(have[n].start_date)) if n in have else None,
                          'end_date': _fd(_shift_year(have[n].end_date)) if n in have else None}
                         for n, nm in ((1, 'First Term'), (2, 'Second Term'), (3, 'Third Term'))],
               'urgent': bool(cur['state'] == 'ended' or (cur['days_left'] is not None and cur['days_left'] <= 60))}

    alerts = []
    if not cur and rows:
        alerts.append({'tone': 'bad', 'icon': 'fa-triangle-exclamation',
                       'text': 'No session is current — pick the one you are in.'})
    if cur and not cur['terms']:
        alerts.append({'tone': 'mid', 'icon': 'fa-calendar-plus',
                       'text': f'{cur["name"]} has no terms yet.', 'link': url_for('academics.terms_list'), 'link_label': 'Add terms'})
    newer = [r for r in rows if cur and r['name'] > cur['name'] and r['state'] == 'running']
    if newer:
        alerts.append({'tone': 'info', 'icon': 'fa-forward', 'text': f'{newer[0]["name"]} has started — make it current.',
                       'activate': newer[0]['id']})

    return _render({
        'page': 'sessions',
        'sessions': rows, 'current_id': cur['id'] if cur else None,
        'next': nxt, 'alerts': alerts,
        'add_url': url_for('academics.add_session'),
        'urls': {'terms': url_for('academics.terms_list'), 'setup': url_for('academics.term_setup'),
                 'copy': url_for('academics.copy_term_setup'),
                 'promotion': url_for('promotion.index') if can_access_module('promotion') else None},
    })


@academics_bp.route('/sessions/add', methods=['GET', 'POST'])
@login_required
def add_session():
    """Add new academic session"""
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            start_date = parse_date(request.form.get('start_date'))
            end_date = parse_date(request.form.get('end_date'))
            is_active = request.form.get('is_active') == 'on'
            
            # Validate
            if not name:
                return _err('Session name is required.', url_for('academics.add_session'))
            if AcademicSession.query.filter_by(name=name).first():
                return _err('A session with this name already exists.', url_for('academics.add_session'))

            # If setting as active, deactivate others
            if is_active:
                AcademicSession.query.update({AcademicSession.is_active: False}, synchronize_session=False)

            session = AcademicSession(
                name=name, start_date=start_date, end_date=end_date, is_active=is_active)
            db.session.add(session)
            db.session.flush()
            made_terms = 0
            if request.form.get('with_terms') == 'on':
                # Copy the current session's term pattern one year on (or plain
                # First/Second/Third Term without dates when there is none).
                src = AcademicSession.query.filter(AcademicSession.id != session.id,
                                                   AcademicSession.is_active == True).first() \
                    if not is_active else None
                if src is None:
                    src = (AcademicSession.query.filter(AcademicSession.id != session.id)
                           .order_by(AcademicSession.name.desc()).first())
                have = {t.term_number: t for t in (src.terms.all() if src else [])}
                pattern = [(n, nm, have.get(n)) for n, nm in ((1, 'First Term'), (2, 'Second Term'), (3, 'Third Term'))]
                for n, nm, t in pattern:
                    nt = Term(session_id=session.id, term_number=n, name=nm,
                              start_date=_shift_year(t.start_date) if t else None,
                              end_date=_shift_year(t.end_date) if t else None)
                    db.session.add(nt)
                    db.session.flush()
                    if nt.start_date and nt.end_date:
                        for wn, mon, fri in get_weeks_in_range(nt.start_date, nt.end_date):
                            db.session.add(Week(term_id=nt.id, week_number=wn, start_date=mon, end_date=fri))
                    made_terms += 1
            db.session.commit()
            if is_active:
                # A brand-new session has no terms yet — clear the active term so
                # term-scoped pages don't keep showing the old session, and drop the
                # admin's time-travel override.
                Term.query.update({Term.is_active: False}, synchronize_session=False)
                if made_terms:
                    first = Term.query.filter_by(session_id=session.id).order_by(Term.term_number).first()
                    first.is_active = True
                db.session.commit()
                from flask import session as _flask_session
                _flask_session.pop('view_session_id', None)
            return _ok(f'{name} created' + (f' with {made_terms} terms.' if made_terms else '.'),
                       url_for('academics.sessions_list'))

        except Exception as e:
            db.session.rollback()
            return _err(f'Error creating session: {str(e)}', url_for('academics.add_session'))

    return _render({'page': 'add_session', 'submit_url': url_for('academics.add_session'),
                    'cancel_url': url_for('academics.sessions_list')})


@academics_bp.route('/sessions/<int:session_id>/activate', methods=['POST'])
@login_required
def activate_session(session_id):
    """Set a session as active — and move the active TERM into it.

    Almost every page scopes by ``get_active_term()`` (results, finance,
    attendance, report cards, …), which on the live path returns the ``is_active``
    Term. Flipping only the session's ``is_active`` would leave the active term in
    the *old* session, so those pages wouldn't switch. So we also activate a term
    of the chosen session (the one covering today, else its latest term), and clear
    the acting admin's personal time-travel override so they see the new live
    session immediately."""
    from datetime import date as _date
    try:
        session_obj = db.get_or_404(AcademicSession, session_id)
        AcademicSession.query.update({AcademicSession.is_active: False}, synchronize_session=False)
        session_obj.is_active = True

        terms = Term.query.filter_by(session_id=session_obj.id).all()
        Term.query.update({Term.is_active: False}, synchronize_session=False)
        if terms:
            today = _date.today()
            pick = next((t for t in terms
                         if t.start_date and t.end_date and t.start_date <= today <= t.end_date), None)
            if pick is None:
                pick = max(terms, key=lambda t: (t.term_number or 0))
            pick.is_active = True
        db.session.commit()

        # Drop the acting admin's read-only time-travel so their view follows the
        # new live session (otherwise the override would mask the switch).
        from flask import session as _flask_session
        _flask_session.pop('view_session_id', None)

        msg = f'{session_obj.name} is now the active session.'
        if not terms:
            msg += ' Add a term to this session so term-based pages have data.'
        return _ok(msg, url_for('academics.sessions_list'))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('academics.sessions_list'))


@academics_bp.route('/sessions/<int:session_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_session(session_id):
    """Edit an academic session"""
    session = db.get_or_404(AcademicSession, session_id)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            start_date = parse_date(request.form.get('start_date'))
            end_date = parse_date(request.form.get('end_date'))
            
            if not name:
                return _err('Session name is required.', url_for('academics.edit_session', session_id=session_id))
            existing = AcademicSession.query.filter(
                AcademicSession.name == name, AcademicSession.id != session_id).first()
            if existing:
                return _err('A session with this name already exists.', url_for('academics.edit_session', session_id=session_id))

            session.name = name
            session.start_date = start_date
            session.end_date = end_date
            db.session.commit()
            return _ok('Session updated successfully!', url_for('academics.sessions_list'))

        except Exception as e:
            db.session.rollback()
            return _err(f'Error updating session: {str(e)}', url_for('academics.edit_session', session_id=session_id))

    return _render({
        'page': 'edit_session',
        'session': {'id': session.id, 'name': session.name,
                    'start_date': session.start_date.isoformat() if session.start_date else '',
                    'end_date': session.end_date.isoformat() if session.end_date else ''},
        'submit_url': url_for('academics.edit_session', session_id=session.id),
        'cancel_url': url_for('academics.sessions_list')})


# ============================================================================
# TERMS
# ============================================================================

@academics_bp.route('/terms')
@login_required
def terms_list():
    Term_NAMES = {1: 'First Term', 2: 'Second Term', 3: 'Third Term'}
    """Terms grouped by session as a timeline: status, progress, readiness
    counts and in-place actions (add, set dates, activate)."""
    from sqlalchemy import func
    terms = Term.query.join(AcademicSession).order_by(
        AcademicSession.name.desc(), Term.term_number).all()
    sessions = AcademicSession.query.order_by(AcademicSession.name.desc()).all()
    today = date.today()
    ids = [t.id for t in terms] or [-1]
    weeks = dict(db.session.query(Week.term_id, func.count(Week.id)).filter(Week.term_id.in_(ids)).group_by(Week.term_id).all())
    hols = dict(db.session.query(Holiday.term_id, func.count(Holiday.id)).filter(Holiday.term_id.in_(ids)).group_by(Holiday.term_id).all())
    classes = dict(db.session.query(ClassArmAssignment.term_id, func.count(ClassArmAssignment.id))
                   .filter(ClassArmAssignment.term_id.in_(ids)).group_by(ClassArmAssignment.term_id).all())
    pupils = dict(db.session.query(ClassArmAssignment.term_id, func.count(StudentEnrollment.id))
                  .join(StudentEnrollment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
                  .filter(ClassArmAssignment.term_id.in_(ids), StudentEnrollment.is_active == True)
                  .group_by(ClassArmAssignment.term_id).all())

    def row(t):
        st, prog, week, left = 'nodates', None, None, None
        if t.start_date and t.end_date:
            total = max(1, (t.end_date - t.start_date).days)
            if today < t.start_date:
                st, left = 'upcoming', (t.start_date - today).days
            elif today > t.end_date:
                st, prog = 'ended', 100
            else:
                st, prog, left = 'running', round((today - t.start_date).days / total * 100), (t.end_date - today).days
                w = Week.query.filter(Week.term_id == t.id, Week.start_date <= today,
                                      Week.end_date >= today - timedelta(days=2)).first()
                week = w.week_number if w else None
        return {'id': t.id, 'name': t.name, 'number': t.term_number, 'is_active': bool(t.is_active),
                'session': t.session.name if t.session else '', 'session_id': t.session_id,
                'start_date': _fd(t.start_date), 'end_date': _fd(t.end_date),
                'start_iso': t.start_date.isoformat() if t.start_date else '',
                'end_iso': t.end_date.isoformat() if t.end_date else '',
                'state': st, 'progress': prog, 'week': week, 'days': left,
                'weeks': weeks.get(t.id, 0), 'holidays': hols.get(t.id, 0),
                'classes': classes.get(t.id, 0), 'students': pupils.get(t.id, 0),
                'results_published': bool(getattr(t, 'results_published', False)),
                'view_url': url_for('academics.view_term', term_id=t.id),
                'edit_url': url_for('academics.edit_term', term_id=t.id),
                'setup_url': url_for('academics.term_setup', term_id=t.id),
                'activate_url': url_for('academics.activate_term', term_id=t.id)}

    rows = [row(t) for t in terms]
    by_session = {}
    for r in rows:
        by_session.setdefault(r['session_id'], []).append(r)

    # Things worth a decision: active term ending with no next term, overlaps, missing dates.
    alerts = []
    act = next((r for r in rows if r['is_active']), None)
    chrono = sorted(terms, key=lambda t: (t.session.name if t.session else '', t.term_number))
    if act:
        t = next(x for x in terms if x.id == act['id'])
        i = chrono.index(t)
        nxt = chrono[i + 1] if i + 1 < len(chrono) else None
        if t.end_date and (t.end_date - today).days <= 30:
            if not nxt:
                when = (f'ends in {(t.end_date - today).days} days' if t.end_date >= today else 'has ended')
                if t.term_number < 3:
                    alerts.append({'tone': 'mid', 'icon': 'fa-calendar-plus',
                                   'text': f'{act["name"]} {when} and {Term_NAMES[t.term_number + 1]} isn’t created yet.',
                                   'add': {'session_id': t.session_id, 'term_number': t.term_number + 1}})
                else:
                    alerts.append({'tone': 'mid', 'icon': 'fa-calendar-plus',
                                   'text': f'{act["name"]} {when} — create next session and its First Term.',
                                   'link': url_for('academics.add_session'), 'link_label': 'New session'})
            elif t.end_date < today and nxt.start_date and nxt.start_date <= today:
                alerts.append({'tone': 'info', 'icon': 'fa-bolt',
                               'text': f'{nxt.full_name} has started — make it the active term.', 'activate': nxt.id})
    elif rows:
        alerts.append({'tone': 'bad', 'icon': 'fa-triangle-exclamation', 'text': 'No term is active — attendance and score entry are paused.'})
    for sid, ts in by_session.items():
        dated = sorted([x for x in terms if x.session_id == sid and x.start_date and x.end_date], key=lambda x: x.start_date)
        for a_, b_ in zip(dated, dated[1:]):
            if b_.start_date <= a_.end_date:
                alerts.append({'tone': 'bad', 'icon': 'fa-code-merge',
                               'text': f'{a_.full_name} and {b_.name} overlap — check their dates.'})
    nod = [r for r in rows if r['state'] == 'nodates' and (r['is_active'] or r['session_id'] == (act or {}).get('session_id'))]
    for r in nod[:2]:
        alerts.append({'tone': 'mid', 'icon': 'fa-calendar-xmark', 'text': f'{r["name"]} {r["session"]} has no dates.', 'dates': r['id']})

    return _render({
        'page': 'terms',
        'terms': rows,
        'sessions': [{'id': s.id, 'name': s.name, 'is_active': bool(s.is_active),
                      'terms': sorted(by_session.get(s.id, []), key=lambda r: r['number'])} for s in sessions],
        'active_id': act['id'] if act else None,
        'alerts': alerts,
        'urls': {'setup': url_for('academics.term_setup'), 'add': url_for('academics.add_term'),
                 'sessions': url_for('academics.sessions_list')},
    })


@academics_bp.route('/terms/add', methods=['GET', 'POST'])
@login_required
def add_term():
    """Add new term"""
    sessions = AcademicSession.query.order_by(AcademicSession.name.desc()).all()
    
    if request.method == 'POST':
        try:
            session_id = request.form.get('session_id', type=int)
            term_number = request.form.get('term_number', type=int)
            start_date = parse_date(request.form.get('start_date'))
            end_date = parse_date(request.form.get('end_date'))
            is_active = request.form.get('is_active') == 'on'
            
            # Validate
            if not session_id or not term_number:
                return _err('Session and term number are required.', url_for('academics.add_term'))
            existing = Term.query.filter_by(
                session_id=session_id, term_number=term_number).first()
            if existing:
                return _err('This term already exists for this session.', url_for('academics.add_term'))
            
            # Get term name
            term_names = {1: 'First Term', 2: 'Second Term', 3: 'Third Term'}
            term_name = term_names.get(term_number, f'Term {term_number}')
            
            # If setting as active, deactivate others
            if is_active:
                Term.query.update({Term.is_active: False})
            
            term = Term(
                session_id=session_id,
                term_number=term_number,
                name=term_name,
                start_date=start_date,
                end_date=end_date,
                is_active=is_active
            )
            db.session.add(term)
            db.session.flush()
            
            # Auto-generate weeks if dates provided
            if start_date and end_date:
                weeks = get_weeks_in_range(start_date, end_date)
                for week_num, mon, fri in weeks:
                    week = Week(
                        term_id=term.id,
                        week_number=week_num,
                        start_date=mon,
                        end_date=fri
                    )
                    db.session.add(week)
            
            db.session.commit()
            return _ok('Term created successfully!', url_for('academics.terms_list'))

        except Exception as e:
            db.session.rollback()
            return _err(f'Error creating term: {str(e)}', url_for('academics.add_term'))

    return _render({
        'page': 'add_term',
        'sessions': [{'id': s.id, 'name': s.name} for s in sessions],
        'submit_url': url_for('academics.add_term'),
        'cancel_url': url_for('academics.terms_list')})


@academics_bp.route('/terms/<int:term_id>/activate', methods=['POST'])
@login_required
def activate_term(term_id):
    """Set a term as active"""
    try:
        Term.query.update({Term.is_active: False})
        
        term = db.get_or_404(Term, term_id)
        term.is_active = True
        
        # Also activate the parent session
        AcademicSession.query.update({AcademicSession.is_active: False})
        term.session.is_active = True

        db.session.commit()

        # Drop the acting admin's read-only time-travel so their view follows the
        # newly activated term (otherwise the override would mask the switch).
        from flask import session as _flask_session
        _flask_session.pop('view_session_id', None)

        return _ok(f'{term.full_name} is now the active term.', url_for('academics.terms_list'))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('academics.terms_list'))


@academics_bp.route('/setup')
@login_required
def term_setup():
    """Term readiness: a grouped checklist (calendar, classes, teaching, fees)
    where each step shows its status, why it matters, and a one-tap fix —
    many of them done in place (activate, set dates, generate weeks, copy
    last term's classes / subjects / fees)."""
    from utils.access_control import can_write_module, can_access_module
    from models import ClassSubject, SchoolSettings
    term_id = request.args.get('term_id', type=int)
    active_session = AcademicSession.query.filter_by(is_active=True).first()
    term = db.session.get(Term, term_id) if term_id else get_active_term()
    terms = Term.query.join(AcademicSession).order_by(
        AcademicSession.name.desc(), Term.term_number.desc()).all()
    # Chronological order → the term just before this one is the copy source.
    chrono = sorted(terms, key=lambda t: (t.session.name if t.session else '', t.term_number))
    prev = None
    if term and term in chrono:
        i = chrono.index(term)
        prev = chrono[i - 1] if i > 0 else None

    can_acad = can_write_module('academics')
    can_subj = can_write_module('results')
    show_fees = can_access_module('finance')
    can_fin = show_fees and can_write_module('finance')
    today = date.today()

    def link(label, url):
        return {'kind': 'link', 'label': label, 'url': url}

    def post(label, url, fields=None, confirm=None, icon=None):
        return {'kind': 'post', 'label': label, 'url': url, 'fields': fields or {},
                'confirm': confirm, 'icon': icon}

    steps, info = [], {}
    if term:
        tid = term.id
        weeks = Week.query.filter_by(term_id=tid).count()
        expected_weeks = len(get_weeks_in_range(term.start_date, term.end_date)) \
            if term.start_date and term.end_date else 0
        holidays = Holiday.query.filter_by(term_id=tid).count()
        asg = ClassArmAssignment.query.filter_by(term_id=tid).all()
        aids = [a.id for a in asg] or [-1]
        no_teacher = [a.display_name for a in asg if not (a.form_teacher_name or '').strip()]
        enrolled = StudentEnrollment.query.filter(
            StudentEnrollment.class_arm_assignment_id.in_(aids),
            StudentEnrollment.is_active == True).count()
        active_students = Student.query.filter_by(is_active=True).count() \
            if hasattr(Student, 'is_active') else Student.query.count()
        empty_classes = [a.display_name for a in asg
                         if a.enrollments.filter_by(is_active=True).count() == 0]
        class_ids = {a.class_id for a in asg}
        cs = ClassSubject.query.filter_by(term_id=tid, is_active=True).all()
        cls_with_subj = {c.class_id for c in cs}
        no_subj = sorted({a.school_class.name for a in asg
                          if a.class_id not in cls_with_subj and a.school_class})
        no_subj_teacher = sum(1 for c in cs if not (c.teacher_name or '').strip())
        prev_asg = ClassArmAssignment.query.filter_by(term_id=prev.id).count() if prev else 0
        prev_cs = ClassSubject.query.filter_by(term_id=prev.id, is_active=True).count() if prev else 0
        term_url = url_for('academics.view_term', term_id=tid)
        asg_url = url_for('academics.assignments_list', term_id=tid)
        subj_url = url_for('subjects.class_subjects_list', term_id=tid)

        # ---- Calendar ----
        steps.append({'key': 'session', 'group': 'calendar', 'icon': 'fa-calendar',
                      'title': 'Academic session is active', 'done': active_session is not None,
                      'detail': active_session.name if active_session else 'No session is active',
                      'why': 'Every term, class and result belongs to a session.',
                      'action': None if active_session else (link('Open sessions', url_for('academics.sessions_list')) if can_acad else None)})
        steps.append({'key': 'active', 'group': 'calendar', 'icon': 'fa-bolt',
                      'title': 'Term is the active term', 'done': bool(term.is_active),
                      'detail': 'Active now' if term.is_active else 'Not active — attendance and score entry use the active term',
                      'why': 'Teachers mark attendance and enter scores for the active term.',
                      'action': None if term.is_active or not can_acad else post(
                          'Make active', url_for('academics.activate_term', term_id=tid),
                          confirm=f'Make {term.full_name} the active term for everyone?', icon='fa-bolt')})
        has_dates = bool(term.start_date and term.end_date)
        steps.append({'key': 'dates', 'group': 'calendar', 'icon': 'fa-calendar-days',
                      'title': 'Start and end dates set', 'done': has_dates,
                      'detail': f'{_fd(term.start_date)} – {_fd(term.end_date)}' if has_dates else 'Dates not set',
                      'why': 'Dates drive the weeks, attendance days and the term progress bar.',
                      'action': {'kind': 'dates', 'label': 'Change dates' if has_dates else 'Set dates',
                                 'url': url_for('academics.edit_term', term_id=tid)} if can_acad else None})
        steps.append({'key': 'weeks', 'group': 'calendar', 'icon': 'fa-table-columns',
                      'title': 'School weeks created', 'done': weeks > 0,
                      'detail': (f'{weeks} weeks' + (f' (dates suggest {expected_weeks})' if expected_weeks and expected_weeks != weeks else ''))
                                if weeks else ('No weeks yet' if has_dates else 'Set the dates first'),
                      'warn': bool(weeks and expected_weeks and expected_weeks != weeks),
                      'why': 'Weekly attendance, lesson notes and timetables are organised by week.',
                      'action': (post('Regenerate weeks' if weeks else 'Generate weeks',
                                      url_for('academics.generate_weeks', term_id=tid),
                                      confirm=('This replaces the existing weeks with ones built from the term dates.' if weeks else None),
                                      icon='fa-wand-magic-sparkles')
                                 if can_acad and has_dates and (not weeks or expected_weeks != weeks) else
                                 (link('View weeks', term_url) if weeks else None))})
        steps.append({'key': 'holidays', 'group': 'calendar', 'icon': 'fa-umbrella-beach', 'optional': True,
                      'title': 'Holidays and mid-term break', 'done': holidays > 0,
                      'detail': f'{holidays} marked' if holidays else 'None marked',
                      'why': 'Holidays are skipped when counting school days and attendance.',
                      'action': link('Add holidays' if not holidays else 'Manage', term_url) if can_acad else link('View', term_url)})

        # ---- Classes & students ----
        copy_cls = post(f'Copy from {prev.full_name}', url_for('academics.copy_term_setup'),
                        {'from_term_id': prev.id, 'to_term_id': tid, 'copy_enrollments': 'on'},
                        confirm=f'Copy the classes and the students in them from {prev.full_name}?', icon='fa-copy') \
            if prev and prev_asg and can_acad else None
        steps.append({'key': 'classes', 'group': 'classes', 'icon': 'fa-school',
                      'title': 'Classes opened for the term', 'done': len(asg) > 0,
                      'detail': f'{len(asg)} class{"es" if len(asg) != 1 else ""}' if asg else 'No classes yet',
                      'why': 'Students, subjects and results are attached to a class for each term.',
                      'action': (copy_cls if not asg and copy_cls else link('Open class setup' if asg else 'Set up classes', asg_url))})
        steps.append({'key': 'students', 'group': 'classes', 'icon': 'fa-user-graduate',
                      'title': 'Students placed in classes', 'done': enrolled > 0,
                      'detail': (f'{enrolled} of {active_students} students placed' if asg else 'Open classes first'),
                      'warn': bool(enrolled and enrolled < active_students),
                      'note': (f'{active_students - enrolled} student{"s" if active_students - enrolled != 1 else ""} not in a class'
                               if enrolled and enrolled < active_students else
                               (f'Empty: {", ".join(empty_classes[:4])}{"…" if len(empty_classes) > 4 else ""}' if empty_classes and enrolled else None)),
                      'why': 'Only placed students appear on attendance registers and score sheets.',
                      'action': (copy_cls if asg and not enrolled and copy_cls else link('Place students', asg_url)) if asg else None})
        steps.append({'key': 'form_teachers', 'group': 'classes', 'icon': 'fa-chalkboard-user', 'optional': True,
                      'title': 'Form teachers assigned', 'done': bool(asg) and not no_teacher,
                      'detail': (f'{len(asg) - len(no_teacher)} of {len(asg)} classes' if asg else 'Open classes first'),
                      'note': (f'Missing: {", ".join(no_teacher[:4])}{"…" if len(no_teacher) > 4 else ""}' if asg and no_teacher else None),
                      'why': 'Form teachers write report-card comments and mark daily attendance.',
                      'action': link('Assign', asg_url) if asg else None})

        # ---- Teaching & results ----
        copy_subj = post(f'Copy from {prev.full_name}', url_for('subjects.copy_class_subjects'),
                         {'from_term_id': prev.id, 'to_term_id': tid},
                         confirm=f'Copy every class’s subjects and subject teachers from {prev.full_name}?', icon='fa-copy') \
            if prev and prev_cs and can_subj else None
        steps.append({'key': 'subjects', 'group': 'teaching', 'icon': 'fa-book',
                      'title': 'Subjects set for each class', 'done': bool(asg) and not no_subj and bool(cs),
                      'detail': (f'{len(class_ids) - len(no_subj)} of {len(class_ids)} classes have subjects' if asg else 'Open classes first'),
                      'note': (f'No subjects: {", ".join(no_subj[:4])}{"…" if len(no_subj) > 4 else ""}' if asg and no_subj and cs else None),
                      'why': 'Score sheets, broadsheets and report cards list the class’s subjects.',
                      'action': (copy_subj if not cs and copy_subj else link('Class subjects', subj_url)) if asg else None})
        steps.append({'key': 'subject_teachers', 'group': 'teaching', 'icon': 'fa-person-chalkboard', 'optional': True,
                      'title': 'Subject teachers named', 'done': bool(cs) and no_subj_teacher == 0,
                      'detail': (f'{len(cs) - no_subj_teacher} of {len(cs)} class subjects' if cs else 'Set subjects first'),
                      'why': 'Teachers see only their own subjects when entering scores.',
                      'action': link('Assign teachers', subj_url) if cs else None})

        # ---- Fees ----
        if show_fees:
            from models import FeeStructure
            fs = FeeStructure.query.filter_by(term_id=tid, is_active=True).all()
            fee_cls = {f.class_id for f in fs}
            no_fee = sorted({a.school_class.name for a in asg if a.class_id not in fee_cls and a.school_class})
            prev_fs = FeeStructure.query.filter_by(term_id=prev.id, is_active=True).count() if prev else 0
            fin_url = url_for('finance.structure', term_id=tid)
            copy_fee = post(f'Copy from {prev.full_name}', url_for('finance.copy_structure'),
                            {'from_term_id': prev.id, 'to_term_id': tid},
                            confirm=f'Copy all school fees from {prev.full_name}? You can adjust amounts afterwards.', icon='fa-copy') \
                if prev and prev_fs and can_fin else None
            steps.append({'key': 'fees', 'group': 'fees', 'icon': 'fa-money-bill-wave', 'optional': True,
                          'title': 'School fees set', 'done': bool(fs) and not no_fee,
                          'detail': (f'{len(class_ids) - len(no_fee)} of {len(class_ids)} classes have fees' if asg else
                                     (f'{len(fee_cls)} classes have fees' if fs else 'No fees set')),
                          'note': (f'No fees: {", ".join(no_fee[:4])}{"…" if len(no_fee) > 4 else ""}' if fs and no_fee else None),
                          'why': 'Bills, balances and defaulter lists come from the fee structure.',
                          'action': copy_fee if not fs and copy_fee else link('Fee structure', fin_url)})

        # ---- Term timeline ----
        if has_dates:
            total = max(1, (term.end_date - term.start_date).days)
            gone = min(max((today - term.start_date).days, 0), total)
            cur_week = Week.query.filter(Week.term_id == tid, Week.start_date <= today,
                                         Week.end_date >= today - timedelta(days=2)).first()
            info = {'start': _fd(term.start_date), 'end': _fd(term.end_date),
                    'progress': round(gone / total * 100),
                    'state': 'upcoming' if today < term.start_date else ('ended' if today > term.end_date else 'running'),
                    'days_left': max((term.end_date - today).days, 0),
                    'days_to_start': max((term.start_date - today).days, 0),
                    'week': cur_week.week_number if cur_week else None, 'weeks': weeks}
        info.update({'classes': len(asg), 'students': enrolled, 'active_students': active_students,
                     'subjects': len(cs), 'holidays': holidays})

        by = {s['key']: s for s in steps}
        ok = lambda *ks: all(by[k]['done'] for k in ks if k in by)
        unlocks = [
            {'label': 'Attendance', 'icon': 'fa-user-check', 'ready': ok('active', 'weeks', 'classes', 'students'),
             'needs': 'active term, weeks and placed students'},
            {'label': 'Score entry & CBT', 'icon': 'fa-pen-to-square', 'ready': ok('active', 'classes', 'students', 'subjects'),
             'needs': 'active term, placed students and class subjects'},
            {'label': 'Report cards', 'icon': 'fa-file-lines', 'ready': ok('classes', 'students', 'subjects', 'form_teachers'),
             'needs': 'subjects and form teachers'},
        ]
        if show_fees:
            unlocks.append({'label': 'Fee billing', 'icon': 'fa-wallet', 'ready': ok('classes', 'students', 'fees'),
                            'needs': 'placed students and a fee structure'})
    else:
        unlocks = []

    required = [s for s in steps if not s.get('optional')]
    done = sum(1 for s in required if s['done'])
    return _render({
        'page': 'setup',
        'term': {'id': term.id, 'full_name': term.full_name, 'is_active': bool(term.is_active),
                 'session': term.session.name if term.session else ''} if term else None,
        'prev_term': prev.full_name if prev else None,
        'info': info, 'unlocks': unlocks,
        'steps': [{**s, 'done': bool(s['done']), 'optional': bool(s.get('optional')),
                   'warn': bool(s.get('warn'))} for s in steps],
        'groups': [g for g in [
            {'key': 'calendar', 'label': 'Term calendar', 'icon': 'fa-calendar-days'},
            {'key': 'classes', 'label': 'Classes & students', 'icon': 'fa-school'},
            {'key': 'teaching', 'label': 'Subjects & teachers', 'icon': 'fa-book'},
            {'key': 'fees', 'label': 'Fees', 'icon': 'fa-wallet'},
        ] if any(s['group'] == g['key'] for s in steps)],
        'done': done, 'required': len(required),
        'optional_done': sum(1 for s in steps if s.get('optional') and s['done']),
        'optional_total': sum(1 for s in steps if s.get('optional')),
        'term_id': term.id if term else '', 'can_write': can_acad,
        'term_dates': {'start_date': term.start_date.isoformat() if term and term.start_date else '',
                       'end_date': term.end_date.isoformat() if term and term.end_date else ''},
        'terms': [{'id': t.id, 'full_name': t.full_name, 'is_active': bool(t.is_active)} for t in terms],
        'self_url': url_for('academics.term_setup'),
        'urls': {'terms': url_for('academics.terms_list'), 'add_term': url_for('academics.add_term'),
                 'sessions': url_for('academics.sessions_list'),
                 'assignments': url_for('academics.assignments_list')},
    })


@academics_bp.route('/terms/<int:term_id>')
@login_required
def view_term(term_id):
    """One term's calendar: progress, every week as Mon–Fri day dots (register
    taken / missed / holiday / upcoming), holidays grouped into breaks, and
    in-place week / date / holiday actions."""
    from sqlalchemy import func
    from models import Attendance
    term = db.get_or_404(Term, term_id)
    weeks = term.weeks.order_by(Week.week_number).all()
    holidays = term.holidays.order_by(Holiday.date).all()
    last_id = weeks[-1].id if weeks else None
    today = timeutil.today()
    hol = {h.date: h for h in holidays}
    # Classes that should take a register: those with students this term.
    n_classes = (db.session.query(func.count(func.distinct(StudentEnrollment.class_arm_assignment_id)))
                 .join(ClassArmAssignment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
                 .filter(ClassArmAssignment.term_id == term.id, StudentEnrollment.is_active == True).scalar() or 0)
    # Per school day: how many classes took the register.
    marked = dict(db.session.query(Attendance.date, func.count(func.distinct(StudentEnrollment.class_arm_assignment_id)))
                  .join(StudentEnrollment, Attendance.enrollment_id == StudentEnrollment.id)
                  .filter(Attendance.week_id.in_([w.id for w in weeks] or [-1]))
                  .group_by(Attendance.date).all())
    att_per_week = dict(db.session.query(Attendance.week_id, func.count(Attendance.id))
                        .filter(Attendance.week_id.in_([w.id for w in weeks] or [-1]))
                        .group_by(Attendance.week_id).all())
    wk_rows, past_days, taken_days, cur_week = [], 0, 0, None
    slots_taken = 0   # class-days with a register
    for w in weeks:
        days = []
        d = w.start_date
        while d <= w.end_date:
            if d.weekday() < 5:
                h = hol.get(d)
                n = marked.get(d, 0)
                if h:
                    st = 'holiday'
                elif d > today:
                    st = 'future'
                elif n:
                    st = 'full' if n_classes and n >= n_classes else 'part'
                else:
                    st = 'missed'
                if st in ('full', 'part', 'missed'):
                    past_days += 1
                    taken_days += 1 if st != 'missed' else 0
                    slots_taken += min(n, n_classes) if n_classes else 0
                days.append({'date': d.isoformat(), 'day': d.strftime('%a'), 'n': d.day, 'status': st,
                             'classes': n, 'reason': h.reason if h else None})
            d += timedelta(days=1)
        is_cur = w.start_date <= today <= w.end_date + timedelta(days=2)
        if is_cur:
            cur_week = w.week_number
        wk_rows.append({'id': w.id, 'week_number': w.week_number,
                        'start_date': _fd(w.start_date), 'end_date': _fd(w.end_date),
                        'label': f'{w.start_date.strftime("%d %b")} – {w.end_date.strftime("%d %b")}',
                        'is_last': w.id == last_id, 'current': is_cur, 'days': days,
                        'attendance': att_per_week.get(w.id, 0),
                        'delete_url': url_for('academics.delete_week', week_id=w.id)})

    # Holidays grouped into breaks: consecutive school days with the same reason.
    breaks = []
    for h in holidays:
        prev = breaks[-1] if breaks else None
        gap_ok = prev and (h.date - prev['_end']).days <= 3 and all(
            (prev['_end'] + timedelta(days=i)).weekday() >= 5 for i in range(1, (h.date - prev['_end']).days))
        if prev and gap_ok and prev['reason'] == h.reason and prev['type'] == (h.holiday_type or ''):
            prev['_end'] = h.date
            prev['ids'].append(h.id)
        else:
            breaks.append({'reason': h.reason, 'type': h.holiday_type or '', '_start': h.date, '_end': h.date,
                           'ids': [h.id]})
    for b in breaks:
        b['days'] = len(b['ids'])
        b['label'] = (_fd(b['_start']) if b['_start'] == b['_end']
                      else f'{b["_start"].strftime("%d %b")} – {_fd(b["_end"])}')
        b['past'] = b['_end'] < today
        b.pop('_start'); b.pop('_end')

    state, prog = 'nodates', None
    if term.start_date and term.end_date:
        total = max(1, (term.end_date - term.start_date).days)
        if today < term.start_date:
            state = 'upcoming'
        elif today > term.end_date:
            state, prog = 'ended', 100
        else:
            state, prog = 'running', round((today - term.start_date).days / total * 100)
    expected = len(get_weeks_in_range(term.start_date, term.end_date)) if term.start_date and term.end_date else 0
    school_days = sum(1 for w in wk_rows for x in w['days'] if x['status'] != 'holiday')
    siblings = (Term.query.join(AcademicSession).order_by(AcademicSession.name.desc(), Term.term_number.desc()).all())
    return _render({
        'page': 'view_term',
        'term': {'id': term.id, 'full_name': term.full_name, 'name': term.name,
                 'session': term.session.name if term.session else '',
                 'is_active': bool(term.is_active), 'has_start': term.start_date is not None,
                 'start_date': _fd(term.start_date), 'end_date': _fd(term.end_date),
                 'start_iso': term.start_date.isoformat() if term.start_date else '',
                 'end_iso': term.end_date.isoformat() if term.end_date else '',
                 'state': state, 'progress': prog,
                 'days_left': max((term.end_date - today).days, 0) if term.end_date and state == 'running' else None,
                 'days_to_start': (term.start_date - today).days if state == 'upcoming' else None},
        'stats': {'weeks': len(weeks), 'expected_weeks': expected, 'current_week': cur_week,
                  'school_days': school_days, 'holiday_days': len(holidays),
                  'past_days': past_days, 'taken_days': taken_days, 'classes': n_classes,
                  'coverage': (round(slots_taken / (n_classes * past_days) * 100) if n_classes and past_days else None)},
        'weeks': wk_rows,
        'breaks': breaks,
        'holidays': [{'id': h.id, 'date': _fd(h.date), 'holiday_type': h.holiday_type or '',
                      'reason': h.reason,
                      'delete_url': url_for('academics.delete_holiday', holiday_id=h.id)} for h in holidays],
        'terms': [{'id': t.id, 'label': t.full_name, 'url': url_for('academics.view_term', term_id=t.id)} for t in siblings],
        'urls': {'edit': url_for('academics.edit_term', term_id=term.id),
                 'add_week': url_for('academics.add_next_week', term_id=term.id),
                 'generate_weeks': url_for('academics.generate_weeks', term_id=term.id),
                 'add_holiday': url_for('academics.add_holiday', term_id=term.id),
                 'remove_holidays': url_for('academics.remove_holidays', term_id=term.id),
                 'setup': url_for('academics.term_setup', term_id=term.id),
                 'terms': url_for('academics.terms_list'),
                 'attendance': url_for('attendance.attendance_app')},
    })


@academics_bp.route('/terms/<int:term_id>/holidays/remove', methods=['POST'])
@login_required
def remove_holidays(term_id):
    """Remove a whole break (several holiday days) in one go."""
    ids = [int(x) for x in request.form.getlist('ids') if str(x).isdigit()] or \
          [int(x) for x in (request.form.get('ids') or '').split(',') if x.strip().isdigit()]
    try:
        rows = Holiday.query.filter(Holiday.term_id == term_id, Holiday.id.in_(ids or [-1])).all()
        for h in rows:
            db.session.delete(h)
        db.session.commit()
        from utils.audit import log_action
        log_action('academics.holiday_delete', detail=f'{len(rows)} day(s) term={term_id}',
                   target_type='term', target_id=term_id)
        return _ok(f'{len(rows)} holiday day{"s" if len(rows) != 1 else ""} removed.',
                   url_for('academics.view_term', term_id=term_id))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('academics.view_term', term_id=term_id))


def _rebuild_weeks(term):
    """Rebuild a term's Mon–Fri weeks from its dates WITHOUT losing attendance.
    Register rows point at a week, so existing Week rows are reused (renumbered
    and re-dated) rather than deleted, every attendance row is re-pointed at the
    week that now contains its date, and only weeks nothing refers to are
    removed. Returns the number of weeks."""
    from models import Attendance
    ranges = get_weeks_in_range(term.start_date, term.end_date)
    old = Week.query.filter_by(term_id=term.id).order_by(Week.start_date, Week.id).all()
    weeks = []
    for i, (num, mon, fri) in enumerate(ranges):
        if i < len(old):
            w = old[i]
            w.week_number, w.start_date, w.end_date = num, mon, fri
        else:
            w = Week(term_id=term.id, week_number=num, start_date=mon, end_date=fri)
            db.session.add(w)
        weeks.append(w)
    db.session.flush()
    spare = old[len(ranges):]
    all_ids = [w.id for w in old] + [w.id for w in weeks]
    if all_ids:
        for a in Attendance.query.filter(Attendance.week_id.in_(set(all_ids))).all():
            home = next((w for w in weeks if w.start_date <= a.date <= w.end_date + timedelta(days=2)), None)
            if home is not None and a.week_id != home.id:
                a.week_id = home.id
    db.session.flush()
    for w in spare:
        if not Attendance.query.filter_by(week_id=w.id).first():
            db.session.delete(w)
        else:   # attendance outside the new dates: keep it, after the last week
            w.week_number = len(ranges) + 1 + spare.index(w)
    return len(ranges)


@academics_bp.route('/terms/<int:term_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_term(term_id):
    """Edit a term's dates"""
    term = db.get_or_404(Term, term_id)
    sessions = AcademicSession.query.order_by(AcademicSession.name.desc()).all()
    
    if request.method == 'POST':
        try:
            start_date = parse_date(request.form.get('start_date'))
            end_date = parse_date(request.form.get('end_date'))
            regenerate_weeks = request.form.get('regenerate_weeks') == 'on'
            
            term.start_date = start_date
            term.end_date = end_date
            
            # Optionally regenerate weeks
            if regenerate_weeks and start_date and end_date:
                _rebuild_weeks(term)

            db.session.commit()
            return _ok('Term updated successfully!', url_for('academics.view_term', term_id=term_id))

        except Exception as e:
            db.session.rollback()
            return _err(f'Error updating term: {str(e)}', url_for('academics.edit_term', term_id=term_id))

    return _render({
        'page': 'edit_term',
        'term': {'id': term.id, 'full_name': term.full_name, 'name': term.name,
                 'session': term.session.name if term.session else '',
                 'start_date': term.start_date.isoformat() if term.start_date else '',
                 'end_date': term.end_date.isoformat() if term.end_date else ''},
        'submit_url': url_for('academics.edit_term', term_id=term.id),
        'cancel_url': url_for('academics.view_term', term_id=term.id)})


# ============================================================================
# WEEKS
# ============================================================================

@academics_bp.route('/terms/<int:term_id>/weeks/add', methods=['POST'])
@login_required
def add_next_week(term_id):
    """Add the next week to a term"""
    term = db.get_or_404(Term, term_id)
    
    try:
        # Get the last week for this term
        last_week = Week.query.filter_by(term_id=term_id).order_by(Week.week_number.desc()).first()
        
        if last_week:
            # Calculate next week based on last week
            new_week_number = last_week.week_number + 1
            new_start_date = last_week.start_date + timedelta(days=7)
            new_end_date = last_week.end_date + timedelta(days=7)
        else:
            # First week - use term start date or today
            new_week_number = 1
            if term.start_date:
                # Find the Monday of or after the start date
                start = term.start_date
                while start.weekday() != 0:  # 0 = Monday
                    start += timedelta(days=1)
                new_start_date = start
            else:
                # Use next Monday from today
                today = timeutil.today()
                days_until_monday = (7 - today.weekday()) % 7
                if days_until_monday == 0:
                    days_until_monday = 7
                new_start_date = today + timedelta(days=days_until_monday)
            
            new_end_date = new_start_date + timedelta(days=4)  # Friday
        
        # Check max weeks (15)
        if new_week_number > 15:
            return _err('Maximum of 15 weeks reached for this term.',
                        url_for('academics.view_term', term_id=term_id))

        week = Week(
            term_id=term.id,
            week_number=new_week_number,
            start_date=new_start_date,
            end_date=new_end_date
        )
        db.session.add(week)
        db.session.commit()
        return _ok(f'Week {new_week_number} added ({new_start_date.strftime("%d %b")} - {new_end_date.strftime("%d %b %Y")})!',
                   url_for('academics.view_term', term_id=term_id))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('academics.view_term', term_id=term_id))


@academics_bp.route('/weeks/<int:week_id>/delete', methods=['POST'])
@login_required
def delete_week(week_id):
    """Delete a week (only the last week can be deleted)"""
    week = db.get_or_404(Week, week_id)
    term_id = week.term_id
    
    try:
        # Verify this is the last week
        last_week = Week.query.filter_by(term_id=term_id).order_by(Week.week_number.desc()).first()
        
        if week.id != last_week.id:
            return _err('Only the last week can be deleted.', url_for('academics.view_term', term_id=term_id))

        # Delete associated attendance records first
        from models import Attendance
        Attendance.query.filter_by(week_id=week_id).delete()

        n = week.week_number
        db.session.delete(week)
        db.session.commit()
        from utils.audit import log_action
        log_action('academics.week_delete', detail=f'week={n} term={term_id}',
                   target_type='week', target_id=week_id)
        return _ok(f'Week {n} deleted.', url_for('academics.view_term', term_id=term_id))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('academics.view_term', term_id=term_id))


@academics_bp.route('/terms/<int:term_id>/weeks/generate', methods=['POST'])
@login_required
def generate_weeks(term_id):
    """Generate weeks for a term"""
    term = db.get_or_404(Term, term_id)
    
    if not term.start_date or not term.end_date:
        return _err('Please set term start and end dates first.', url_for('academics.view_term', term_id=term_id))

    try:
        weeks = range(_rebuild_weeks(term))
        db.session.commit()
        return _ok(f'{len(weeks)} weeks generated successfully!', url_for('academics.view_term', term_id=term_id))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('academics.view_term', term_id=term_id))


# ============================================================================
# HOLIDAYS
# ============================================================================

@academics_bp.route('/terms/<int:term_id>/holidays/add', methods=['POST'])
@login_required
def add_holiday(term_id):
    """Add a holiday (single day or a date range, e.g. a one-week mid-term break)."""
    try:
        from datetime import timedelta
        start = parse_date(request.form.get('date'))
        end = parse_date(request.form.get('end_date')) or start
        reason = request.form.get('reason', '').strip()
        holiday_type = request.form.get('holiday_type', 'Public Holiday')

        if not start or not reason:
            return _err('Date and reason are required.', url_for('academics.view_term', term_id=term_id))
        if end < start:
            start, end = end, start
        if (end - start).days > 60:
            return _err('That range is longer than 60 days — please check the dates.',
                        url_for('academics.view_term', term_id=term_id))

        taken = {h.date for h in Holiday.query.filter_by(term_id=term_id).all()}
        added = skipped = 0
        d = start
        while d <= end:
            if d.weekday() >= 5:          # weekends are already non-school days
                pass
            elif d in taken:
                skipped += 1
            else:
                db.session.add(Holiday(term_id=term_id, date=d, reason=reason,
                                       holiday_type=holiday_type))
                added += 1
            d += timedelta(days=1)
        db.session.commit()

        if added and end != start:
            msg = (f'{reason}: {added} day(s) marked '
                   f'({start.strftime("%d %b")} – {end.strftime("%d %b %Y")}).')
        elif added:
            msg = 'Holiday added successfully!'
        else:
            msg = 'No new days to add — those dates are already holidays or weekends.'
        if skipped:
            msg += f' {skipped} already-marked day(s) skipped.'
        return _ok(msg, url_for('academics.view_term', term_id=term_id)) if added \
            else _err(msg, url_for('academics.view_term', term_id=term_id))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('academics.view_term', term_id=term_id))


@academics_bp.route('/holidays/<int:holiday_id>/delete', methods=['POST'])
@login_required
def delete_holiday(holiday_id):
    """Delete a holiday"""
    holiday = db.get_or_404(Holiday, holiday_id)
    term_id = holiday.term_id
    try:
        label = getattr(holiday, 'name', None) or getattr(holiday, 'title', None)
        db.session.delete(holiday)
        db.session.commit()
        from utils.audit import log_action
        log_action('academics.holiday_delete', detail=f'{label} term={term_id}',
                   target_type='holiday', target_id=holiday_id)
        return _ok('Holiday deleted.', url_for('academics.view_term', term_id=term_id))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('academics.view_term', term_id=term_id))


# ============================================================================
# CLASSES
# ============================================================================

_SECTIONS = [('nursery', 'Nursery'), ('primary', 'Primary'), ('junior', 'Junior secondary'),
             ('senior', 'Senior secondary'), ('other', 'Other')]
_STD_CLASS_SUGGEST = [('JSS1', 1, 'junior'), ('JSS2', 2, 'junior'), ('JSS3', 3, 'junior'),
                      ('SSS1', 4, 'senior'), ('SSS2', 5, 'senior'), ('SSS3', 6, 'senior')]


def _class_section(c):
    if c.section:
        return c.section
    n = (c.name or '').upper().replace(' ', '')
    if n.startswith('SS'):
        return 'senior'
    if n.startswith('JS'):
        return 'junior'
    if 'NUR' in n or n.startswith(('KG', 'PRE', 'CRE')):
        return 'nursery'
    if n.startswith(('BAS', 'PRI', 'GRADE', 'YEAR')):
        return 'primary'
    return 'other'


def _structure_term():
    t = get_active_term()
    return t


def _term_counts(term):
    """Per (class_id, arm_id) for the term: students enrolled and the assignment id."""
    from sqlalchemy import func
    if not term:
        return {}
    rows = (db.session.query(ClassArmAssignment.id, ClassArmAssignment.class_id, ClassArmAssignment.arm_id,
                             ClassArmAssignment.form_teacher_name,
                             func.count(StudentEnrollment.id))
            .outerjoin(StudentEnrollment, (StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
                       & (StudentEnrollment.is_active == True))
            .filter(ClassArmAssignment.term_id == term.id)
            .group_by(ClassArmAssignment.id).all())
    from utils.branch_scope import scope_query
    try:
        allowed = {a.id for a in scope_query(ClassArmAssignment.query.filter_by(term_id=term.id), ClassArmAssignment).all()}
    except Exception:
        allowed = None
    out = {}
    for aid, cid, arm_id, ft, n in rows:
        if allowed is not None and aid not in allowed:
            continue
        cur = out.setdefault((cid, arm_id), {'students': 0, 'ids': [], 'teacher': bool(ft)})
        cur['students'] += n
        cur['ids'].append(aid)
    return out


@academics_bp.route('/classes')
@login_required
def classes_list():
    """Classes grouped by section, with this term's arms, students and subjects,
    level checks (promotion follows the level order) and quick-add of the
    standard JSS/SSS classes."""
    from models import ClassSubject
    from sqlalchemy import func
    classes = SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.level, SchoolClass.name).all()
    term = _structure_term()
    counts = _term_counts(term)
    subj = dict(db.session.query(ClassSubject.class_id, func.count(func.distinct(ClassSubject.subject_id)))
                .filter(ClassSubject.term_id == (term.id if term else -1), ClassSubject.is_active == True)
                .group_by(ClassSubject.class_id).all())
    arm_names = {a.id: (a.name, bool(a.is_default)) for a in ClassArm.query.all()}

    def row(c):
        mine = sorted([(arm_names.get(arm, ('?', False)), v) for (cid, arm), v in counts.items() if cid == c.id],
                      key=lambda x: x[0][0])
        return {'id': c.id, 'name': c.name, 'level': c.level, 'description': c.description or '',
                'section': _class_section(c), 'section_set': bool(c.section),
                'arms': [{'name': nm, 'default': dflt, 'students': v['students']} for (nm, dflt), v in mine],
                'students': sum(v['students'] for _, v in mine), 'subjects': subj.get(c.id, 0),
                'opened': bool(mine),
                'edit_url': url_for('academics.edit_class', class_id=c.id),
                'delete_url': url_for('academics.delete_class', class_id=c.id)}

    rows = [row(c) for c in classes]
    alerts = []
    by_level = {}
    for r in rows:
        by_level.setdefault(r['level'], []).append(r['name'])
    dup = [(lv, ns) for lv, ns in sorted(by_level.items()) if len(ns) > 1]
    for lv, ns in dup[:3]:
        alerts.append({'tone': 'mid', 'icon': 'fa-layer-group',
                       'text': f'{" and ".join(ns)} share level {lv} — promotion can’t tell which comes next.'})
    levels = sorted(by_level)
    gaps = [lv for lv in range(levels[0], levels[-1]) if lv not in by_level] if levels else []
    if gaps:
        alerts.append({'tone': 'info', 'icon': 'fa-stairs',
                       'text': f'No class at level {", ".join(map(str, gaps[:4]))} — promotion moves students up one level at a time.'})
    closed = [r['name'] for r in rows if not r['opened']]
    if term and closed and len(closed) < len(rows):
        alerts.append({'tone': 'info', 'icon': 'fa-door-closed',
                       'text': f'Not opened for {term.name}: {", ".join(closed[:5])}{"…" if len(closed) > 5 else ""}.',
                       'link': url_for('academics.assignments_list', term_id=term.id), 'link_label': 'Class setup'})
    names = {r['name'].upper().replace(' ', '') for r in rows}
    suggest = [{'name': n, 'level': lv, 'section': sec} for n, lv, sec in _STD_CLASS_SUGGEST if n not in names]
    return _render({
        'page': 'classes',
        'classes': rows, 'alerts': alerts, 'suggest': suggest,
        'sections': [{'key': k, 'label': l} for k, l in _SECTIONS],
        'term': term.full_name if term else None,
        'next_level': (max(levels) + 1) if levels else 1,
        'totals': {'classes': len(rows), 'opened': sum(1 for r in rows if r['opened']),
                   'students': sum(r['students'] for r in rows),
                   'arms': len({a['name'] for r in rows for a in r['arms'] if not a['default']})},
        'add_url': url_for('academics.add_class'),
        'urls': {'classes': url_for('academics.classes_list'), 'arms': url_for('academics.arms_list'),
                 'assignments': url_for('academics.assignments_list')}})


@academics_bp.route('/classes/add', methods=['POST'])
@login_required
def add_class():
    """Add a new class"""
    try:
        name = request.form.get('name', '').strip().upper()
        level = request.form.get('level', type=int)
        description = request.form.get('description', '').strip()

        if not name or not level:
            return _err('Class name and level are required.', url_for('academics.classes_list'))
        if SchoolClass.query.filter_by(name=name).first():
            return _err('A class with this name already exists.', url_for('academics.classes_list'))

        section = request.form.get('section') or None
        db.session.add(SchoolClass(name=name, level=level, description=description,
                                   section=section if section in {k for k, _ in _SECTIONS[:4]} else None))
        db.session.commit()
        return _ok('Class added successfully!', url_for('academics.classes_list'))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('academics.classes_list'))


@academics_bp.route('/classes/<int:class_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_class(class_id):
    """Edit a class"""
    school_class = db.get_or_404(SchoolClass, class_id)

    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip().upper()
            level = request.form.get('level', type=int)
            description = request.form.get('description', '').strip()

            if not name or not level:
                return _err('Class name and level are required.', url_for('academics.edit_class', class_id=class_id))
            existing = SchoolClass.query.filter(SchoolClass.name == name, SchoolClass.id != class_id).first()
            if existing:
                return _err('A class with this name already exists.', url_for('academics.edit_class', class_id=class_id))

            school_class.name = name
            school_class.level = level
            school_class.description = description
            if 'section' in request.form:
                sec = request.form.get('section') or None
                school_class.section = sec if sec in {k for k, _ in _SECTIONS[:4]} else None
            db.session.commit()
            return _ok('Class updated!', url_for('academics.classes_list'))
        except Exception as e:
            db.session.rollback()
            return _err(f'Error: {str(e)}', url_for('academics.edit_class', class_id=class_id))

    return _render({
        'page': 'edit_class',
        'school_class': {'id': school_class.id, 'name': school_class.name,
                          'level': school_class.level, 'description': school_class.description or ''},
        'submit_url': url_for('academics.edit_class', class_id=school_class.id),
        'cancel_url': url_for('academics.classes_list'),
    })


@academics_bp.route('/classes/<int:class_id>/delete', methods=['POST'])
@login_required
def delete_class(class_id):
    """Delete (deactivate) a class. Existing class-arm assignments and
    enrollments that reference it are left untouched — class pickers already
    filter to is_active, so it simply stops being offered going forward."""
    school_class = db.get_or_404(SchoolClass, class_id)
    try:
        school_class.is_active = False
        db.session.commit()
        from utils.audit import log_action
        log_action('class.delete', detail=school_class.name, target=school_class)
        return _ok('Class deleted!', url_for('academics.classes_list'))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('academics.classes_list'))


# ============================================================================
# CLASS ARMS
# ============================================================================

@academics_bp.route('/arms')
@login_required
def arms_list():
    """Arms with where they're used this term (classes × arms grid), the
    'school uses arms' switch and quick-add suggestions. The hidden default
    'General' arm is never shown."""
    from models import SchoolSettings
    uses = bool(SchoolSettings.get('uses_class_arms', True))
    arms = ClassArm.query.filter_by(is_default=False, is_active=True).order_by(ClassArm.name).all()
    classes = SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.level, SchoolClass.name).all()
    term = _structure_term()
    counts = _term_counts(term)
    grid = []
    for c in classes:
        cells = {}
        for a in arms:
            v = counts.get((c.id, a.id))
            if v:
                cells[str(a.id)] = {'students': v['students'],
                                    'url': url_for('academics.view_assignment', assignment_id=v['ids'][0])}
        grid.append({'id': c.id, 'name': c.name, 'cells': cells})
    rows = []
    for a in arms:
        used = [(c, counts[(c.id, a.id)]) for c in classes if (c.id, a.id) in counts]
        rows.append({'id': a.id, 'name': a.name, 'description': a.description or '',
                     'classes': [c.name for c, _ in used], 'students': sum(v['students'] for _, v in used),
                     'edit_url': url_for('academics.edit_arm', arm_id=a.id),
                     'delete_url': url_for('academics.delete_arm', arm_id=a.id)})
    have = {a.name.lower() for a in ClassArm.query.all()}
    pool = ['A', 'B', 'C', 'D', 'Gold', 'Silver', 'Diamond', 'Ruby', 'Emerald', 'Science', 'Art', 'Commercial']
    return _render({
        'page': 'arms', 'uses_arms': uses,
        'arms': rows, 'grid': grid, 'term': term.full_name if term else None,
        'suggest': [n for n in pool if n.lower() not in have][:6],
        'unused': [r['name'] for r in rows if not r['classes']],
        'add_url': url_for('academics.add_arm'),
        'uses_url': url_for('academics.set_uses_arms'),
        'urls': {'classes': url_for('academics.classes_list'), 'arms': url_for('academics.arms_list'),
                 'assignments': url_for('academics.assignments_list')}})


@academics_bp.route('/arms/add', methods=['POST'])
@login_required
def add_arm():
    """Add a new class arm"""
    try:
        name = request.form.get('name', '').strip().title()
        description = request.form.get('description', '').strip()

        if not name:
            return _err('Arm name is required.', url_for('academics.arms_list'))
        if ClassArm.query.filter_by(name=name).first():
            return _err('An arm with this name already exists.', url_for('academics.arms_list'))

        db.session.add(ClassArm(name=name, description=description))
        db.session.commit()
        return _ok('Arm added successfully!', url_for('academics.arms_list'))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('academics.arms_list'))


@academics_bp.route('/arms/<int:arm_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_arm(arm_id):
    """Edit a class arm"""
    arm = db.get_or_404(ClassArm, arm_id)
    if arm.is_default:
        return _err('The default arm cannot be edited.', url_for('academics.arms_list'))

    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip().title()
            description = request.form.get('description', '').strip()

            if not name:
                return _err('Arm name is required.', url_for('academics.edit_arm', arm_id=arm_id))
            existing = ClassArm.query.filter(ClassArm.name == name, ClassArm.id != arm_id).first()
            if existing:
                return _err('An arm with this name already exists.', url_for('academics.edit_arm', arm_id=arm_id))

            arm.name = name
            arm.description = description
            db.session.commit()
            return _ok('Arm updated!', url_for('academics.arms_list'))
        except Exception as e:
            db.session.rollback()
            return _err(f'Error: {str(e)}', url_for('academics.edit_arm', arm_id=arm_id))

    return _render({
        'page': 'edit_arm',
        'arm': {'id': arm.id, 'name': arm.name, 'description': arm.description or ''},
        'submit_url': url_for('academics.edit_arm', arm_id=arm.id),
        'cancel_url': url_for('academics.arms_list'),
    })


@academics_bp.route('/arms/<int:arm_id>/delete', methods=['POST'])
@login_required
def delete_arm(arm_id):
    """Delete (deactivate) a class arm. Existing class-arm assignments and
    enrollments that reference it are left untouched — arm pickers already
    filter to is_active, so it simply stops being offered going forward."""
    arm = db.get_or_404(ClassArm, arm_id)
    if arm.is_default:
        return _err('The default arm cannot be deleted.', url_for('academics.arms_list'))
    try:
        arm.is_active = False
        db.session.commit()
        from utils.audit import log_action
        log_action('arm.delete', detail=arm.name, target=arm)
        return _ok('Arm deleted!', url_for('academics.arms_list'))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('academics.arms_list'))


# ============================================================================
# CLASS ARM ASSIGNMENTS
# ============================================================================

@academics_bp.route('/assignments')
@login_required
def assignments_list():
    """List class arm assignments for a term"""
    term_id = request.args.get('term_id', type=int)
    
    terms = Term.query.join(AcademicSession).order_by(
        AcademicSession.name.desc(),
        Term.term_number
    ).all()
    
    if not term_id:
        active_term = get_active_term()
        if active_term:
            term_id = active_term.id
    
    assignments = []
    selected_term = None
    if term_id:
        selected_term = db.session.get(Term, term_id)
        from utils.branch_scope import scope_query
        assignments = scope_query(ClassArmAssignment.query.filter_by(term_id=term_id), ClassArmAssignment).join(
            SchoolClass
        ).order_by(SchoolClass.level).all()
    
    from models import SchoolSettings
    uses_arms = bool(SchoolSettings.get('uses_class_arms', True))
    classes = SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.level).all()
    # Real arms only — the hidden default 'General' arm is never a pickable choice.
    arms = ClassArm.query.filter_by(is_active=True, is_default=False).order_by(ClassArm.name).all()

    # Active enrolments per class-arm by gender, in one query (the tabs show
    # totals and a boys/girls split for every arm).
    gcount = {}
    if assignments:
        rows = (db.session.query(StudentEnrollment.class_arm_assignment_id, Student.gender, db.func.count())
                .join(Student, Student.id == StudentEnrollment.student_id)
                .filter(StudentEnrollment.is_active == True,
                        StudentEnrollment.class_arm_assignment_id.in_([a.id for a in assignments]))
                .group_by(StudentEnrollment.class_arm_assignment_id, Student.gender).all())
        for aid, g, n in rows:
            gcount.setdefault(aid, {})[g if g in ('Male', 'Female') else 'Other'] = n

    # Decision helpers: who has no class this term, and last term to copy from.
    unplaced, prev_term, ever = 0, None, set()
    if selected_term:
        placed = {sid for (sid,) in db.session.query(StudentEnrollment.student_id)
                  .join(ClassArmAssignment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
                  .filter(ClassArmAssignment.term_id == selected_term.id, StudentEnrollment.is_active == True).all()}
        try:
            from utils.branch_scope import scope_query as _sq
            act_ids = {s.id for s in _sq(Student.query.filter_by(is_active=True), Student).all()}
        except Exception:
            act_ids = {s.id for s in Student.query.filter_by(is_active=True).all()}
        unplaced = len(act_ids - placed)
        chrono = sorted(terms, key=lambda t: (t.session.name if t.session else '', t.term_number))
        if selected_term in chrono:
            i = chrono.index(selected_term)
            for t in reversed(chrono[:i]):
                n = ClassArmAssignment.query.filter_by(term_id=t.id).count()
                if n:
                    prev_term = {'id': t.id, 'name': t.full_name, 'classes': n}
                    break
        if assignments:
            ever = {aid for (aid,) in db.session.query(StudentEnrollment.class_arm_assignment_id)
                    .filter(StudentEnrollment.class_arm_assignment_id.in_([a.id for a in assignments])).distinct().all()}
    return _render({
        'page': 'assignments',
        'term_id': term_id or '',
        'uses_arms': uses_arms,
        'selected_term': ({'id': selected_term.id, 'name': selected_term.name}
                          if selected_term else None),
        'terms': [{'id': t.id, 'full_name': t.full_name} for t in terms],
        'classes': [{'id': c.id, 'name': c.name} for c in classes],
        'arms': [{'id': a.id, 'name': a.name} for a in arms],
        'assignments': [{'id': a.id,
                         'name': a.display_name,
                         'class_id': a.class_id,
                         'arm': a.arm_label,
                         'arm_id': a.arm_id,
                         'form_teacher': a.form_teacher_name or '',
                         'form_teacher_phone': a.form_teacher_phone or '',
                         'students': sum(gcount.get(a.id, {}).values()),
                         'boys': gcount.get(a.id, {}).get('Male', 0),
                         'girls': gcount.get(a.id, {}).get('Female', 0),
                         'view_url': url_for('academics.view_assignment', assignment_id=a.id),
                         'ever': a.id in ever,
                         'delete_url': url_for('academics.delete_assignment', assignment_id=a.id),
                         'edit_teacher_url': url_for('academics.edit_assignment_teacher', assignment_id=a.id)}
                        for a in assignments],
        'unplaced': unplaced, 'prev_term': prev_term,
        'urls': {'classes': url_for('academics.classes_list'), 'arms': url_for('academics.arms_list'),
                 'assignments': url_for('academics.assignments_list'),
                 'copy': url_for('academics.copy_term_setup'), 'students': url_for('main.students_list'),
                 'setup': url_for('academics.term_setup', term_id=term_id) if term_id else url_for('academics.term_setup')},
        'self_url': url_for('academics.assignments_list'),
        'add_url': url_for('academics.add_assignment'),
        'setup_url': url_for('academics.setup_term_classes'),
        'toggle_url': url_for('academics.set_uses_arms')})


@academics_bp.route('/assignments/add', methods=['POST'])
@login_required
def add_assignment():
    """Create a class arm assignment. The arm is optional: when the school
    doesn't use arms (or none is chosen), the hidden default 'General' arm is
    used so the class shows as just 'SSS1'."""
    try:
        term_id = request.form.get('term_id', type=int)
        class_id = request.form.get('class_id', type=int)
        # Accept one arm (arm_id) or many (arm_ids) so several arms of a class can
        # be set up in one go.
        arm_ids = request.form.getlist('arm_ids', type=int)
        single = request.form.get('arm_id', type=int)
        if single and single not in arm_ids:
            arm_ids.append(single)
        arm_ids = [a for a in dict.fromkeys(arm_ids) if a]   # de-dupe, drop 0/None
        form_teacher = request.form.get('form_teacher', '').strip()
        form_teacher_phone = request.form.get('form_teacher_phone', '').strip()

        if not all([term_id, class_id]):
            return _err('Term and class are required.',
                        url_for('academics.assignments_list', term_id=term_id or ''))
        from models import SchoolSettings
        if not arm_ids:                                  # no arm picked
            if bool(SchoolSettings.get('uses_class_arms', True)):
                return _err('Pick at least one arm for this class.',
                            url_for('academics.assignments_list', term_id=term_id))
            arm_ids = [ClassArm.default().id]            # arm-less school -> default arm

        from utils.branch_scope import branch_for_new
        bid = branch_for_new()      # no branch picked -> default branch
        created, skipped = 0, 0
        for arm_id in arm_ids:
            if ClassArmAssignment.query.filter_by(
                    term_id=term_id, class_id=class_id, arm_id=arm_id, branch_id=bid).first():
                skipped += 1
                continue
            db.session.add(ClassArmAssignment(
                term_id=term_id, class_id=class_id, arm_id=arm_id,
                branch_id=bid,
                form_teacher_name=form_teacher or None,
                form_teacher_phone=form_teacher_phone or None))
            created += 1
        db.session.commit()
        if not created:
            return _err('Those class/arm(s) are already set up for this term.',
                        url_for('academics.assignments_list', term_id=term_id))
        msg = f'{created} class/arm(s) set up for the term.'
        if skipped:
            msg += f' {skipped} already existed.'
        return _ok(msg, url_for('academics.assignments_list', term_id=term_id))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('academics.assignments_list', term_id=term_id or ''))


@academics_bp.route('/assignments/<int:assignment_id>/edit-teacher', methods=['POST'])
@login_required
def edit_assignment_teacher(assignment_id):
    """Correct the form (class) teacher's name (and phone) on an existing
    assignment — e.g. a misspelling or the wrong teacher."""
    a = db.get_or_404(ClassArmAssignment, assignment_id)
    from utils.branch_scope import require_branch_access
    require_branch_access(a.branch_id)                # no cross-branch edits
    a.form_teacher_name = (request.form.get('form_teacher', '') or '').strip() or None
    if 'form_teacher_phone' in request.form:
        a.form_teacher_phone = (request.form.get('form_teacher_phone', '') or '').strip() or None
    db.session.commit()
    return _ok('Class teacher updated.', url_for('academics.assignments_list', term_id=a.term_id))


@academics_bp.route('/assignments/<int:assignment_id>/delete', methods=['POST'])
@login_required
def delete_assignment(assignment_id):
    """Close an arm opened by mistake for a term — only while it has never had
    a student (so no attendance, scores or history can be lost)."""
    a = db.get_or_404(ClassArmAssignment, assignment_id)
    from utils.branch_scope import require_branch_access
    require_branch_access(a.branch_id)
    back = url_for('academics.assignments_list', term_id=a.term_id)
    if StudentEnrollment.query.filter_by(class_arm_assignment_id=a.id).first():
        return _err(f'{a.display_name} has (or had) students this term, so it can’t be removed. '
                    'Move them to another arm first.', back)
    try:
        name = a.display_name
        db.session.delete(a)
        db.session.commit()
        from utils.audit import log_action
        log_action('academics.assignment_delete', detail=name, target_type='class_arm_assignment', target_id=assignment_id)
        return _ok(f'{name} removed from this term.', back)
    except Exception as e:
        db.session.rollback()
        return _err(f'Could not remove: {e}', back)


@academics_bp.route('/assignments/setup-all', methods=['POST'])
@login_required
def setup_term_classes():
    """One click for arm-less schools: give every active class a default-arm
    assignment for the term so students can be enrolled without picking arms."""
    term_id = request.form.get('term_id', type=int)
    if not term_id:
        return _err('Select a term first.', url_for('academics.assignments_list'))
    from models import SchoolSettings
    if bool(SchoolSettings.get('uses_class_arms', True)):
        return _err('This is for schools without arms — turn arms off first.',
                    url_for('academics.assignments_list', term_id=term_id))
    try:
        from utils.branch_scope import branch_for_new
        arm = ClassArm.default()
        bid = branch_for_new()
        existing = {a.class_id for a in ClassArmAssignment.query.filter_by(
            term_id=term_id, arm_id=arm.id, branch_id=bid).all()}
        created = 0
        for c in SchoolClass.query.filter_by(is_active=True).all():
            if c.id in existing:
                continue
            db.session.add(ClassArmAssignment(term_id=term_id, class_id=c.id,
                                              arm_id=arm.id, branch_id=bid))
            created += 1
        db.session.commit()
        return _ok(f'{created} class(es) set up for the term.',
                   url_for('academics.assignments_list', term_id=term_id))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('academics.assignments_list', term_id=term_id or ''))


@academics_bp.route('/uses-arms', methods=['POST'])
@login_required
def set_uses_arms():
    """Toggle whether this school streams classes into arms. When turned off the
    default arm is provisioned so class setup needs no arm."""
    from models import SchoolSettings
    on = (request.form.get('uses_arms') or '').strip().lower() in ('1', 'true', 'on', 'yes')
    try:
        SchoolSettings.set('uses_class_arms', on, 'bool', 'School streams classes into arms')
        if not on:
            ClassArm.default()                            # ensure it exists
        db.session.commit()
        return _ok('Saved.', url_for('academics.assignments_list'))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('academics.assignments_list'))


@academics_bp.route('/assignments/<int:assignment_id>')
@login_required
def view_assignment(assignment_id):
    """View class arm assignment and enrolled students"""
    from utils.branch_scope import require_branch_access
    assignment = db.get_or_404(ClassArmAssignment, assignment_id)
    require_branch_access(assignment.branch_id)   # no cross-branch roster
    enrollments = (assignment.enrollments.filter_by(is_active=True)
                  .join(Student, StudentEnrollment.student_id == Student.id)
                  .filter(Student.is_graduated == False)
                  .order_by(Student.surname, Student.first_name).all())

    # Available = active, non-graduated students NOT already actively
    # enrolled in ANY class for this term. A student must be removed from
    # their current class before they can be reassigned, so they only
    # reappear here once freed up.
    active_elsewhere = (
        db.session.query(StudentEnrollment.student_id)
        .join(ClassArmAssignment,
              StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
        .filter(StudentEnrollment.is_active == True,
                ClassArmAssignment.term_id == assignment.term_id)
    )
    q = Student.query.filter(
        Student.is_active == True,
        Student.is_graduated == False,
        ~Student.id.in_(active_elsewhere.scalar_subquery()),
    )
    # Keep the list to this class's branch when the assignment is branch-bound.
    if assignment.branch_id is not None:
        q = q.filter(Student.branch_id == assignment.branch_id)
    available_students = q.order_by(Student.surname, Student.first_name).all()

    # For the "Add students" session filter: the class each available student
    # was in, per session ({session_id: "JSS2 Gold"}; the last term wins).
    from models import Term
    by_session = {}
    av_ids = [s.id for s in available_students]
    if av_ids:
        rows = (db.session.query(StudentEnrollment.student_id, Term.session_id, ClassArmAssignment)
                .join(ClassArmAssignment, ClassArmAssignment.id == StudentEnrollment.class_arm_assignment_id)
                .join(Term, Term.id == ClassArmAssignment.term_id)
                .filter(StudentEnrollment.student_id.in_(av_ids))
                .order_by(Term.session_id, Term.term_number).all())
        for sid, sess_id, caa in rows:
            by_session.setdefault(sid, {})[str(sess_id)] = caa.display_name

    sessions = AcademicSession.query.order_by(AcademicSession.start_date.desc()).all()
    classes = SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.level).all()
    arms = ClassArm.query.filter_by(is_active=True).filter(ClassArm.is_default.isnot(True)).order_by(ClassArm.name).all()

    return _render({
        'page': 'view_assignment',
        'assignment': {'id': assignment.id, 'display_name': assignment.display_name,
                       'term': assignment.term.full_name if assignment.term else '',
                       'term_id': assignment.term_id,
                       'class_name': assignment.school_class.name if assignment.school_class else '',
                       'arm': assignment.arm_label,
                       'form_teacher': assignment.form_teacher_name or '',
                       'form_teacher_phone': assignment.form_teacher_phone or '',
                       'edit_teacher_url': url_for('academics.edit_assignment_teacher', assignment_id=assignment.id),
                       'session_id': assignment.term.session_id if assignment.term else None},
        'enrollments': [{'id': e.id, 'student_id': e.student_id, 'full_name': e.student.full_name,
                         'surname': e.student.surname or '', 'first_name': e.student.first_name or '',
                         'middle_name': e.student.middle_name or '',
                         'student_no': e.student.student_id, 'gender': e.student.gender or '',
                         'view_url': url_for('main.view_student', student_id=e.student_id),
                         'remove_url': url_for('academics.remove_enrollment', enrollment_id=e.id)}
                        for e in enrollments],
        'available_students': [{'id': s.id, 'full_name': s.full_name, 'student_id': s.student_id,
                                'classes': by_session.get(s.id, {})}
                               for s in available_students],
        'sessions': [{'id': s.id, 'name': s.name} for s in sessions],
        'classes': [{'id': c.id, 'name': c.name} for c in classes],
        'arms': [{'id': a.id, 'name': a.name} for a in arms],
        # The other arms of this class this term, for one-tap switching.
        'siblings': [{'id': x.id, 'name': x.display_name, 'arm': x.arm_label,
                      'url': url_for('academics.view_assignment', assignment_id=x.id)}
                     for x in sorted(ClassArmAssignment.query.filter_by(
                         term_id=assignment.term_id, class_id=assignment.class_id,
                         branch_id=assignment.branch_id).all(),
                         key=lambda x: x.arm_label)],
        'back_url': url_for('academics.assignments_list', term_id=assignment.term_id) + f'#class-{assignment.class_id}',
        'enroll_url': url_for('academics.enroll_student', assignment_id=assignment.id),
        'reassign_url': url_for('academics.reassign_students', assignment_id=assignment.id)})


@academics_bp.route('/assignments/<int:assignment_id>/reassign', methods=['POST'])
@login_required
def reassign_students(assignment_id):
    """Move selected students from this class-arm to a different class/arm —
    optionally in a different academic session entirely. Essentially a manual,
    ad-hoc counterpart to bulk promotion: pick who moves, pick where they go.
    If the destination is the SAME session, the student's current enrollment
    for that session is deactivated so they aren't in two classes at once; if
    it's a different session, the old enrollment is simply left as history."""
    from utils.branch_scope import require_branch_access
    assignment = db.get_or_404(ClassArmAssignment, assignment_id)
    require_branch_access(assignment.branch_id)

    student_ids = (request.form.getlist('student_ids[]') or request.form.getlist('student_ids'))
    to_session_id = request.form.get('to_session_id', type=int)
    to_class_id = request.form.get('to_class_id', type=int)
    to_arm_id = request.form.get('to_arm_id', type=int)
    back = url_for('academics.view_assignment', assignment_id=assignment_id)

    if not student_ids:
        return _err('Select at least one student.', back)
    if not (to_session_id and to_class_id and to_arm_id):
        return _err('Select the destination session, class, and arm.', back)

    to_term = Term.query.filter_by(session_id=to_session_id, term_number=1).first()
    if not to_term:
        return _err('The destination session has no First Term set up yet — create its terms first.', back)

    to_assignment = ClassArmAssignment.query.filter_by(
        term_id=to_term.id, class_id=to_class_id, arm_id=to_arm_id).first()
    if not to_assignment:
        return _err('That class/arm isn\'t set up for the destination session\'s First Term yet.', back)
    if to_assignment.branch_id != assignment.branch_id:
        return _err('The destination class belongs to another branch.', back)

    same_session = (to_term.session_id == assignment.term.session_id if assignment.term else False)

    try:
        moved = 0
        for raw in student_ids:
            try:
                sid = int(raw)
            except (TypeError, ValueError):
                continue

            # Don't create a duplicate enrollment for a student already there.
            existing = StudentEnrollment.query.filter_by(
                student_id=sid, class_arm_assignment_id=to_assignment.id).first()
            if existing:
                if not existing.is_active:
                    existing.is_active = True
                    moved += 1
            else:
                db.session.add(StudentEnrollment(student_id=sid, class_arm_assignment_id=to_assignment.id))
                moved += 1

            if same_session:
                # Deactivate every other active enrollment this student has in
                # the destination session's terms, so they don't show up in
                # two classes for the same session at once.
                other = (StudentEnrollment.query.join(ClassArmAssignment)
                        .join(Term, ClassArmAssignment.term_id == Term.id)
                        .filter(StudentEnrollment.student_id == sid,
                                StudentEnrollment.is_active == True,
                                Term.session_id == to_session_id,
                                StudentEnrollment.class_arm_assignment_id != to_assignment.id)
                        .all())
                for o in other:
                    o.is_active = False

        db.session.commit()
        from utils.audit import log_action
        log_action('academics.students_reassign',
                   detail=f'{moved} student(s) -> {to_assignment.display_name} ({to_term.full_name})')
        return _ok(f'{moved} student(s) moved to {to_assignment.display_name} for {to_term.full_name}.', back)
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', back)


@academics_bp.route('/assignments/<int:assignment_id>/enroll', methods=['POST'])
@login_required
def enroll_student(assignment_id):
    """Enroll a student in a class arm"""
    from utils.branch_scope import require_branch_access
    assignment = db.get_or_404(ClassArmAssignment, assignment_id)
    require_branch_access(assignment.branch_id)   # no cross-branch enrolment

    try:
        # Accept both "student_ids[]" and "student_ids" field names.
        student_ids = (request.form.getlist('student_ids[]')
                       or request.form.getlist('student_ids'))

        added = 0          # brand-new enrollments
        reactivated = 0    # previously-removed enrollments brought back
        elsewhere = 0      # already in another class this term — use "Move" instead
        busy = {sid for (sid,) in db.session.query(StudentEnrollment.student_id)
                .join(ClassArmAssignment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
                .filter(ClassArmAssignment.term_id == assignment.term_id,
                        ClassArmAssignment.id != assignment.id,
                        StudentEnrollment.is_active == True).all()}
        for raw in student_ids:
            try:
                sid = int(raw)
            except (TypeError, ValueError):
                continue
            if sid in busy:
                elsewhere += 1
                continue
            # A soft-removed enrollment leaves a row (unique student+assignment),
            # so re-enrolling must REACTIVATE it rather than insert a duplicate.
            existing = StudentEnrollment.query.filter_by(
                student_id=sid,
                class_arm_assignment_id=assignment_id
            ).first()
            if existing:
                if not existing.is_active:
                    existing.is_active = True
                    reactivated += 1
                # already active -> nothing to do
            else:
                db.session.add(StudentEnrollment(
                    student_id=sid,
                    class_arm_assignment_id=assignment_id
                ))
                added += 1

        db.session.commit()
        total = added + reactivated
        msg = (f'{total} student(s) enrolled.' if total
               else 'No new students to enroll — the selected students were already in this class.')
        if elsewhere:
            msg += (f' {elsewhere} already in another class this term — use Move to change their class,'
                    ' so their attendance and scores follow them.')
        return _ok(msg, url_for('academics.view_assignment', assignment_id=assignment_id))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('academics.view_assignment', assignment_id=assignment_id))


@academics_bp.route('/enrollments/<int:enrollment_id>/remove', methods=['POST'])
@login_required
def remove_enrollment(enrollment_id):
    """Remove a student from a class arm"""
    from utils.branch_scope import require_branch_access
    enrollment = db.get_or_404(StudentEnrollment, enrollment_id)
    require_branch_access(enrollment.class_arm_assignment.branch_id)   # no cross-branch unenrol
    assignment_id = enrollment.class_arm_assignment_id

    try:
        enrollment.is_active = False
        db.session.commit()
        from utils.audit import log_action
        log_action('academics.enrollment_remove',
                   detail=f'student={enrollment.student_id} assignment={assignment_id}',
                   target_type='studentenrollment', target_id=enrollment.id)
        return _ok('Student removed from class.', url_for('academics.view_assignment', assignment_id=assignment_id))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('academics.view_assignment', assignment_id=assignment_id))


# ============================================================================
# API ENDPOINTS
# ============================================================================

@academics_bp.route('/api/terms/<int:session_id>')
@login_required
def api_get_terms(session_id):
    """Get terms for a session (AJAX)"""
    terms = Term.query.filter_by(session_id=session_id).order_by(Term.term_number).all()
    return jsonify([{
        'id': t.id,
        'name': t.name,
        'is_active': t.is_active
    } for t in terms])


@academics_bp.route('/api/assignments/<int:term_id>')
@login_required
def api_get_assignments(term_id):
    """Get class arm assignments for a term (AJAX)"""
    assignments = ClassArmAssignment.query.filter_by(term_id=term_id).join(
        SchoolClass
    ).order_by(SchoolClass.level).all()
    
    return jsonify([{
        'id': a.id,
        'name': a.display_name,
        'class_name': a.school_class.name,
        'arm_name': a.arm_label
    } for a in assignments])


@academics_bp.route('/api/weeks/<int:term_id>')
@login_required
def api_get_weeks(term_id):
    """Get weeks for a term (AJAX)"""
    weeks = Week.query.filter_by(term_id=term_id).order_by(Week.week_number).all()
    return jsonify([{
        'id': w.id,
        'week_number': w.week_number,
        'start_date': w.start_date.isoformat(),
        'end_date': w.end_date.isoformat()
    } for w in weeks])


# ============================================================================
# COPY TERM SETUP
# ============================================================================

@academics_bp.route('/copy-term-setup', methods=['GET', 'POST'])
@login_required
def copy_term_setup():
    """Copy class assignments and enrollments from one term to another"""
    if request.method == 'POST':
        try:
            from_term_id = request.form.get('from_term_id', type=int)
            to_term_id = request.form.get('to_term_id', type=int)
            copy_enrollments = request.form.get('copy_enrollments') == 'on'
            
            if not from_term_id or not to_term_id:
                return _err('Select both source and destination terms.', url_for('academics.copy_term_setup'))
            if from_term_id == to_term_id:
                return _err('Source and destination must be different.', url_for('academics.copy_term_setup'))
            
            from_term = db.session.get(Term, from_term_id)
            to_term = db.session.get(Term, to_term_id)
            
            # Get source assignments
            source_assignments = ClassArmAssignment.query.filter_by(term_id=from_term_id).all()
            # Students already in a class in the destination term keep it — copying
            # must not give them a second active class (two registers, split
            # attendance).
            placed = {sid for (sid,) in db.session.query(StudentEnrollment.student_id)
                      .join(ClassArmAssignment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
                      .filter(ClassArmAssignment.term_id == to_term_id, StudentEnrollment.is_active == True).all()}
            
            assignments_copied = 0
            enrollments_copied = 0
            
            for src_assign in source_assignments:
                # Check if already exists
                existing = ClassArmAssignment.query.filter_by(
                    term_id=to_term_id,
                    class_id=src_assign.class_id,
                    arm_id=src_assign.arm_id
                ).first()
                
                if existing:
                    dest_assign = existing
                else:
                    # Create new assignment (inherit the source's branch)
                    dest_assign = ClassArmAssignment(
                        term_id=to_term_id,
                        class_id=src_assign.class_id,
                        arm_id=src_assign.arm_id,
                        branch_id=src_assign.branch_id
                    )
                    db.session.add(dest_assign)
                    db.session.flush()  # Get ID
                    assignments_copied += 1
                
                # Copy enrollments if requested
                if copy_enrollments:
                    src_enrollments = StudentEnrollment.query.filter_by(
                        class_arm_assignment_id=src_assign.id,
                        is_active=True
                    ).all()
                    
                    for src_enroll in src_enrollments:
                        # Check if student already enrolled
                        existing_enroll = StudentEnrollment.query.filter_by(
                            student_id=src_enroll.student_id,
                            class_arm_assignment_id=dest_assign.id
                        ).first()
                        
                        if not existing_enroll and src_enroll.student_id not in placed:
                            placed.add(src_enroll.student_id)
                            new_enroll = StudentEnrollment(
                                student_id=src_enroll.student_id,
                                class_arm_assignment_id=dest_assign.id
                            )
                            db.session.add(new_enroll)
                            enrollments_copied += 1
            
            db.session.commit()

            msg = f'Copied {assignments_copied} class assignments'
            if copy_enrollments:
                msg += f' and {enrollments_copied} student enrollments'
            return _ok(msg + '!', url_for('academics.copy_term_setup'))

        except Exception as e:
            db.session.rollback()
            return _err(f'Error: {str(e)}', url_for('academics.copy_term_setup'))

    # GET - show form
    terms = Term.query.order_by(Term.id.desc()).all()
    return _render({
        'page': 'copy_term_setup',
        'terms': [{'id': t.id, 'full_name': t.full_name, 'is_active': bool(t.is_active)} for t in terms],
        'submit_url': url_for('academics.copy_term_setup'),
        'cancel_url': url_for('academics.assignments_list')})
