"""Events & Calendar routes — month calendar, agenda list, and event CRUD."""
import calendar as _cal
from datetime import datetime, date, timedelta

from flask import (Blueprint, render_template, request, redirect, url_for, flash, jsonify)

from models import db, SchoolEvent, Term
from utils.access_control import login_required

events_bp = Blueprint('events', __name__, url_prefix='/events')

CATEGORIES = ['General', 'Holiday', 'Exam', 'Meeting', 'Activity', 'Sport']
AUDIENCES = ['All', 'Staff', 'Students', 'Parents']
CATEGORY_COLORS = {'Holiday': '#e74a3b', 'Exam': '#7e6cf0', 'Meeting': '#4e73df',
                   'Activity': '#1cc88a', 'Sport': '#fd7e14', 'General': '#11998e'}


def _d(value, default=None):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return default


def _current_user():
    from flask import session
    return session.get('username') or session.get('user') or 'Admin'


def _wants_json():
    return request.headers.get('X-Requested-With') == 'fetch' or request.is_json


def _ok(message, redirect_url=None):
    if _wants_json():
        return jsonify({'ok': True, 'message': message, 'redirect': redirect_url})
    flash(message, 'success')
    return redirect(redirect_url or url_for('events.calendar'))


def _err(message, redirect_url=None, tone='error'):
    if _wants_json():
        return jsonify({'ok': False, 'error': message}), 400
    flash(message, tone)
    return redirect(redirect_url or url_for('events.calendar'))


def _render(payload):
    from utils.spa import render_or_json
    return render_or_json('events/app.html', 'events_json', payload)


def _event_json(e):
    return {
        'id': e.id, 'title': e.title, 'category': e.category, 'color': e.color,
        'audience': e.audience, 'location': e.location,
        'start_time': e.start_time, 'end_time': e.end_time, 'all_day': bool(e.all_day),
        'edit_url': url_for('events.edit_event', event_id=e.id),
        'delete_url': url_for('events.delete_event', event_id=e.id),
    }


@events_bp.route('/')
@login_required
def calendar():
    today = date.today()
    year = request.args.get('year', type=int) or today.year
    month = request.args.get('month', type=int) or today.month
    if month < 1:
        month, year = 12, year - 1
    elif month > 12:
        month, year = 1, year + 1

    # Events overlapping this month.
    first = date(year, month, 1)
    last = date(year, month, _cal.monthrange(year, month)[1])
    events = (SchoolEvent.query
              .filter(SchoolEvent.start_date <= last)
              .filter(db.func.coalesce(SchoolEvent.end_date, SchoolEvent.start_date) >= first)
              .order_by(SchoolEvent.start_date, SchoolEvent.start_time).all())

    # Map each day -> list of events on that day.
    by_day = {}
    for e in events:
        d = max(e.start_date, first)
        end = min(e.last_date, last)
        while d <= end:
            by_day.setdefault(d, []).append(e)
            d += timedelta(days=1)

    cal = _cal.Calendar(firstweekday=6)  # Sunday first
    weeks = cal.monthdatescalendar(year, month)

    prev_m = (first - timedelta(days=1))
    next_m = (last + timedelta(days=1))
    weeks_json = [[{
        'day': day.day, 'iso': day.isoformat(),
        'in_month': day.month == month, 'is_today': day == today,
        'add_url': url_for('events.add_event', date=day.isoformat()),
        'events': [_event_json(e) for e in by_day.get(day, [])],
    } for day in week] for week in weeks]
    return _render({
        'page': 'calendar', 'year': year, 'month': month, 'month_name': _cal.month_name[month],
        'weeks': weeks_json, 'categories': CATEGORIES, 'category_colors': CATEGORY_COLORS,
        'nav': {'prev_url': url_for('events.calendar', year=prev_m.year, month=prev_m.month),
                'next_url': url_for('events.calendar', year=next_m.year, month=next_m.month),
                'today_url': url_for('events.calendar')},
        'urls': {'import': url_for('events.import_calendar'), 'agenda': url_for('events.agenda'),
                 'add_event': url_for('events.add_event')},
    })


@events_bp.route('/list')
@login_required
def agenda():
    category = request.args.get('category')
    upcoming = request.args.get('upcoming', '1')
    q = SchoolEvent.query
    if category:
        q = q.filter_by(category=category)
    if upcoming == '1':
        q = q.filter(db.func.coalesce(SchoolEvent.end_date, SchoolEvent.start_date) >= date.today())
    events = q.order_by(SchoolEvent.start_date, SchoolEvent.start_time).all()

    def row(e):
        date_label = e.start_date.strftime('%a, %d %b %Y')
        if e.end_date:
            date_label += ' – ' + e.end_date.strftime('%d %b')
        time_label = ''
        if e.start_time and not e.all_day:
            time_label = e.start_time + (('–' + e.end_time) if e.end_time else '')
        return {**_event_json(e), 'date_label': date_label, 'time_label': time_label,
                'description': e.description}
    return _render({
        'page': 'agenda', 'events': [row(e) for e in events],
        'category': category or '', 'upcoming': upcoming, 'categories': CATEGORIES,
        'urls': {'calendar': url_for('events.calendar'), 'add_event': url_for('events.add_event'),
                 'self': url_for('events.agenda')},
    })


def _read(e):
    e.title = (request.form.get('title') or '').strip()
    e.description = (request.form.get('description') or '').strip() or None
    e.category = request.form.get('category') or 'General'
    e.start_date = _d(request.form.get('start_date')) or date.today()
    e.end_date = _d(request.form.get('end_date'))
    if e.end_date and e.end_date < e.start_date:
        e.end_date = None
    e.all_day = bool(request.form.get('all_day'))
    e.start_time = (request.form.get('start_time') or '').strip() or None
    e.end_time = (request.form.get('end_time') or '').strip() or None
    e.location = (request.form.get('location') or '').strip() or None
    e.audience = request.form.get('audience') or 'All'
    e.term_id = request.form.get('term_id', type=int) or None


@events_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_event():
    if request.method == 'POST':
        if not request.form.get('title'):
            return _err('Title is required.', url_for('events.add_event'))
        e = SchoolEvent(created_by=_current_user())
        _read(e)
        db.session.add(e)
        db.session.commit()
        return _ok('Event added.',
                   url_for('events.calendar', year=e.start_date.year, month=e.start_date.month))
    preset = _d(request.args.get('date'))
    return _render(_form_payload(None, preset.isoformat() if preset else ''))


def _form_payload(e, preset=''):
    return {
        'page': 'event_form',
        'event': ({
            'id': e.id, 'title': e.title, 'category': e.category, 'audience': e.audience,
            'start_date': e.start_date.isoformat() if e.start_date else '',
            'end_date': e.end_date.isoformat() if e.end_date else '',
            'all_day': bool(e.all_day), 'start_time': e.start_time or '', 'end_time': e.end_time or '',
            'location': e.location or '', 'term_id': e.term_id or '', 'description': e.description or '',
        } if e else None),
        'preset': preset,
        'terms': [{'id': t.id, 'label': t.full_name} for t in Term.query.order_by(Term.id.desc()).all()],
        'categories': CATEGORIES, 'audiences': AUDIENCES,
        'submit_url': url_for('events.edit_event', event_id=e.id) if e else url_for('events.add_event'),
        'delete_url': url_for('events.delete_event', event_id=e.id) if e else None,
        'urls': {'agenda': url_for('events.agenda'), 'calendar': url_for('events.calendar')},
    }


@events_bp.route('/<int:event_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_event(event_id):
    e = db.get_or_404(SchoolEvent, event_id)
    if request.method == 'POST':
        _read(e)
        db.session.commit()
        return _ok('Event updated.', url_for('events.agenda'))
    return _render(_form_payload(e))


@events_bp.route('/<int:event_id>/delete', methods=['POST'])
@login_required
def delete_event(event_id):
    e = db.get_or_404(SchoolEvent, event_id)
    from utils.audit import log_action
    log_action('events.event_delete', detail=getattr(e, 'title', None), target=e)
    db.session.delete(e)
    db.session.commit()
    return _ok('Event deleted.', url_for('events.agenda'))


# ============================================================================
# IMPORT (scan a Word doc / image of the school calendar)
# ============================================================================

@events_bp.route('/import', methods=['GET', 'POST'])
@login_required
def import_calendar():
    from utils import calendar_import
    if request.method == 'POST':
        f = request.files.get('file')
        if not f or not f.filename:
            return _err('Choose a Word document or image to scan.', url_for('events.import_calendar'))
        data = f.read()
        name = f.filename.lower()
        try:
            if name.endswith('.docx'):
                parsed = calendar_import.parse_docx(data)
            elif name.endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tif', '.tiff', '.pdf')):
                parsed = calendar_import.parse_image(data, f.filename)
            else:
                return _err('Unsupported file. Upload a .docx, image, or PDF.', url_for('events.import_calendar'))
        except Exception as e:
            return _err(f'Could not read the file: {e}', url_for('events.import_calendar'))
        if not parsed:
            return _err('No dated activities were detected. Try a clearer scan or add events manually.',
                        url_for('events.import_calendar'), tone='warning')
        rows = [{'start_date': r['start_date'].isoformat() if r.get('start_date') else '',
                 'end_date': r['end_date'].isoformat() if r.get('end_date') else '',
                 'title': r.get('title') or '', 'category': r.get('category') or 'General'} for r in parsed]
        if _wants_json():
            return jsonify({'ok': True, 'rows': rows, 'categories': CATEGORIES,
                            'terms': [{'id': t.id, 'label': t.full_name} for t in Term.query.order_by(Term.id.desc()).all()],
                            'save_url': url_for('events.import_save')})
        return render_template('events/import_review.html', rows=parsed,
            categories=CATEGORIES, terms=Term.query.order_by(Term.id.desc()).all())
    return _render({'page': 'import', 'upload_url': url_for('events.import_calendar'),
                    'urls': {'calendar': url_for('events.calendar')}})


@events_bp.route('/import/save', methods=['POST'])
@login_required
def import_save():
    term_id = request.form.get('term_id', type=int) or None
    count = request.form.get('row_count', type=int) or 0
    user = _current_user()
    saved = 0
    for i in range(count):
        if not request.form.get(f'include_{i}'):
            continue
        title = (request.form.get(f'title_{i}') or '').strip()
        start = _d(request.form.get(f'start_{i}'))
        if not (title and start):
            continue
        end = _d(request.form.get(f'end_{i}'))
        db.session.add(SchoolEvent(
            title=title, start_date=start,
            end_date=end if end and end >= start else None,
            category=request.form.get(f'category_{i}') or 'General',
            all_day=True, audience='All', term_id=term_id, created_by=user))
        saved += 1
    db.session.commit()
    return _ok(f'Imported {saved} event(s) into the calendar.', url_for('events.agenda'))
