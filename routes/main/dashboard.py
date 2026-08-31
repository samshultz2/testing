"""main blueprint — dashboard routes (split from the former routes/main.py)."""
from routes.main import *  # noqa: F401,F403  (blueprint, models, helpers)
# Underscore-prefixed helpers aren't re-exported by ``import *`` — pull them in
# explicitly so the personalization endpoints can use them.
from routes.main import (_dashboard_layout, _block_permitted, _dash_widget_slice,  # noqa: E402
                         DASHBOARD_BLOCK_IDS)


@main_bp.route('/')
@login_required
def dashboard():
    """Main dashboard. The React app (dashboard-app.js) renders the widgets;
    the data is hydrated inline (no extra round-trip) and also available at
    /api/dashboard/data for refresh.

    `/` stays a universally-rendering home for every role (it doubles as the
    common landing + CSRF host); role-aware landing is handled inside the
    payload via `home_focus`, which makes the dashboard finance-first for a
    finance-only staffer instead of showing them an empty academic grid."""
    payload = dashboard_payload()
    return render_template('dashboard.html', dash_json=payload, **payload)


@main_bp.route('/api/dashboard/data')
@login_required
def api_dashboard_data():
    """Dashboard widget data as JSON — permission/branch/teacher scoped exactly
    like the page (only enabled+permitted widgets are computed and returned)."""
    return jsonify(dashboard_payload())


@main_bp.route('/api/dashboard/widgets', methods=['POST'])
@login_required
def api_dashboard_widgets():
    """Save the user's dashboard personalization: which widgets show (Customize),
    the block order (drag-to-arrange) and favourites. Each field is optional, so
    a reorder-only or favourite-only save leaves the others intact. Everything is
    permission-scoped — enabled is gated by module permission via enabled_widgets,
    and a block can only be favourited if the user may see it."""
    from utils.access_control import get_current_user
    data = request.get_json(silent=True) or {}
    sent = data.get('widgets')
    order = data.get('order')
    favorites = data.get('favorites')

    chosen = None
    if sent is not None:
        if not isinstance(sent, list):
            return jsonify({'error': 'widgets must be a list'}), 400
        s = set(sent)
        chosen = [k for k, _, _, _ in DASHBOARD_WIDGETS if k in s]   # registry order
    if order is not None:
        if not isinstance(order, list):
            return jsonify({'error': 'order must be a list'}), 400
        order = [b for b in order if b in DASHBOARD_BLOCK_IDS]
    if favorites is not None:
        if not isinstance(favorites, list):
            return jsonify({'error': 'favorites must be a list'}), 400
        # Can't favourite a block you're not permitted to see.
        favorites = [b for b in favorites
                     if b in DASHBOARD_BLOCK_IDS and _block_permitted(b)]

    user = get_current_user()
    if user:
        user.set_dashboard_layout(enabled=chosen, order=order, favorites=favorites)
        db.session.commit()
    else:
        if chosen is not None:
            session['dashboard_prefs'] = chosen
        if order is not None:
            session['dashboard_order'] = order
        if favorites is not None:
            session['dashboard_favorites'] = favorites
    return jsonify({'ok': True, 'enabled': sorted(enabled_widgets()),
                    'layout': _dashboard_layout()})


@main_bp.route('/api/dashboard/widget/<block_id>')
@login_required
def api_dashboard_widget(block_id):
    """Data for a single dashboard block — true per-widget refresh. Only the
    block's own slice is computed, and only if the user may see it."""
    if block_id not in DASHBOARD_BLOCK_IDS:
        return jsonify({'error': 'unknown widget'}), 404
    if not _block_permitted(block_id):
        return jsonify({'error': 'forbidden'}), 403
    return jsonify(_dash_widget_slice(block_id))


@main_bp.route('/api/dashboard/timetable/slot/<int:slot_id>')
@login_required
def api_dashboard_timetable_slot(slot_id):
    """Drill-down for a period on the Today's-schedule widget: each class arm's
    subject and teacher in that slot today. Branch/teacher-scoped like the glance."""
    from routes.main import _dash_timetable_slot, _teacher_scope
    data = _dash_timetable_slot(get_active_term(), _teacher_scope(), slot_id)
    if data is None:
        return jsonify({'error': 'not found'}), 404
    return jsonify(data)


@main_bp.route('/react-spike')
@login_required
def react_spike():
    """Throwaway page that mounts one React widget (integration spike)."""
    return render_template('spike.html')


@main_bp.route('/dashboard/customize', methods=['GET', 'POST'])
@login_required
def dashboard_customize():
    """Choose which dashboard widgets to show."""
    from utils.access_control import get_current_user
    user = get_current_user()
    if request.method == 'POST':
        chosen = [k for k, _, _, _ in DASHBOARD_WIDGETS if request.form.get(f'w_{k}') == 'on']
        if user:
            user.set_dashboard_widgets(chosen)
            db.session.commit()
        else:
            session['dashboard_prefs'] = chosen
        flash('Dashboard updated.', 'success')
        return redirect(url_for('main.dashboard'))
    return render_template('dashboard_customize.html',
                           widgets=DASHBOARD_WIDGETS, enabled=enabled_widgets())


@main_bp.route('/api/dashboard/stats')
@login_required
def api_dashboard_stats():
    """API endpoint for dashboard statistics"""
    from utils.calculations import get_attendance_statistics

    active_term = get_active_term()

    base = _viewer_student_scope(Student.query.filter_by(is_active=True))
    stats = {
        'total_students': base.count(),
        'male_students': base.filter(Student.gender == 'Male').count(),
        'female_students': base.filter(Student.gender == 'Female').count(),
    }

    if active_term:
        attendance_stats = get_attendance_statistics(active_term.id)
        stats.update(attendance_stats)

    return jsonify(stats)
