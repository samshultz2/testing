"""main blueprint — dashboard routes (split from the former routes/main.py)."""
from routes.main import *  # noqa: F401,F403  (blueprint, models, helpers)


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
    """Save the user's dashboard widget choices (the in-SPA Customize panel).
    Stores choices in registry order; what's actually shown is still gated by
    module permission via enabled_widgets()."""
    from utils.access_control import get_current_user
    data = request.get_json(silent=True) or {}
    sent = data.get('widgets')
    if not isinstance(sent, list):
        return jsonify({'error': 'widgets must be a list'}), 400
    sent = set(sent)
    chosen = [k for k, _, _, _ in DASHBOARD_WIDGETS if k in sent]   # registry order
    user = get_current_user()
    if user:
        user.set_dashboard_widgets(chosen)
        db.session.commit()
    else:
        session['dashboard_prefs'] = chosen
    return jsonify({'ok': True, 'enabled': sorted(enabled_widgets())})


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
