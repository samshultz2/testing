"""Events & Calendar routes — month calendar, agenda list, and event CRUD."""
import calendar as _cal
from datetime import datetime, date, timedelta

from flask import (Blueprint, render_template, request, redirect, url_for, flash)

from models import db, SchoolEvent, Term
from utils.access_control import login_required, is_admin

events_bp = Blueprint('events', __name__, url_prefix='/events')

CATEGORIES = ['General', 'Holiday', 'Exam', 'Meeting', 'Activity', 'Sport']
AUDIENCES = ['All', 'Staff', 'Students', 'Parents']


def _d(value, default=None):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return default


def _current_user():
    from flask import session
    return session.get('username') or session.get('user') or 'Admin'


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
    return render_template('events/calendar.html',
        year=year, month=month, month_name=_cal.month_name[month],
        weeks=weeks, by_day=by_day, today=today, first=first,
        prev_year=prev_m.year, prev_month=prev_m.month,
        next_year=next_m.year, next_month=next_m.month,
        categories=CATEGORIES)


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
    return render_template('events/agenda.html', events=events,
        category=category, upcoming=upcoming, categories=CATEGORIES)


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
            flash('Title is required.', 'error')
            return redirect(url_for('events.add_event'))
        e = SchoolEvent(created_by=_current_user())
        _read(e)
        db.session.add(e)
        db.session.commit()
        flash('Event added.', 'success')
        return redirect(url_for('events.calendar', year=e.start_date.year, month=e.start_date.month))
    preset = _d(request.args.get('date'))
    return render_template('events/event_form.html', event=None, preset=preset,
        terms=Term.query.order_by(Term.id.desc()).all(),
        categories=CATEGORIES, audiences=AUDIENCES)


@events_bp.route('/<int:event_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_event(event_id):
    e = SchoolEvent.query.get_or_404(event_id)
    if request.method == 'POST':
        _read(e)
        db.session.commit()
        flash('Event updated.', 'success')
        return redirect(url_for('events.agenda'))
    return render_template('events/event_form.html', event=e, preset=None,
        terms=Term.query.order_by(Term.id.desc()).all(),
        categories=CATEGORIES, audiences=AUDIENCES)


@events_bp.route('/<int:event_id>/delete', methods=['POST'])
@login_required
def delete_event(event_id):
    e = SchoolEvent.query.get_or_404(event_id)
    db.session.delete(e)
    db.session.commit()
    flash('Event deleted.', 'success')
    return redirect(url_for('events.agenda'))


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
            flash('Choose a Word document or image to scan.', 'error')
            return redirect(url_for('events.import_calendar'))
        data = f.read()
        name = f.filename.lower()
        try:
            if name.endswith('.docx'):
                parsed = calendar_import.parse_docx(data)
            elif name.endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tif', '.tiff', '.pdf')):
                parsed = calendar_import.parse_image(data, f.filename)
            else:
                flash('Unsupported file. Upload a .docx, image, or PDF.', 'error')
                return redirect(url_for('events.import_calendar'))
        except Exception as e:
            flash(f'Could not read the file: {e}', 'error')
            return redirect(url_for('events.import_calendar'))
        if not parsed:
            flash('No dated activities were detected. Try a clearer scan or add events manually.', 'warning')
            return redirect(url_for('events.import_calendar'))
        return render_template('events/import_review.html', rows=parsed,
            categories=CATEGORIES, terms=Term.query.order_by(Term.id.desc()).all())
    return render_template('events/import.html')


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
    flash(f'Imported {saved} event(s) into the calendar.', 'success')
    return redirect(url_for('events.agenda'))
