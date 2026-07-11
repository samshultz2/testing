"""results blueprint — predictions routes (split from the former routes/results.py)."""
from routes.results import *  # noqa: F401,F403


@results_bp.route('/api/predict-jamb/<int:student_id>')
@login_required
def api_predict_jamb(student_id):
    """Get JAMB prediction for a student"""
    require_branch_access(db.get_or_404(Student, student_id).branch_id)
    prediction = AcademicAnalytics.predict_jamb_score(student_id)
    return jsonify(prediction)


@results_bp.route('/predictions')
@login_required
def predictions_dashboard():
    """WAEC-JAMB correlation and predictions dashboard"""
    from utils.exam_analytics import WAECJAMBCorrelation
    
    correlation_data = WAECJAMBCorrelation.get_correlation_analysis()

    from utils import exam_insights
    students = get_sss3_students()
    calibration = exam_insights.calibration_summary(students)

    # Forecast the whole cohort straight from the mocks (Mock WAEC -> WAEC,
    # Mock JAMB -> JAMB) — most students have no real WAEC/JAMB yet.
    session = get_active_session()
    bias = exam_insights.get_jamb_bias()
    cohort = exam_insights.cohort_readiness(
        students, session.id if session else None, calibration=bias)

    # Aggregate JAMB outlook: projected mean ± the measured error, plus a
    # confidence breakdown and the predicted-score distribution.
    outlook = exam_insights.cohort_jamb_outlook(
        students, session.id if session else None, calibration=bias,
        mae=(calibration.get('jamb') or {}).get('mae'))

    return render_template('results/predictions_dashboard.html',
        correlation_data=correlation_data,
        calibration=calibration,
        outlook=outlook,
        cohort=cohort,
        waec_model_url=url_for('results.waec_model_config'),
        focus_url=url_for('results.focus_areas'),
    )


@results_bp.route('/predictions/focus')
@login_required
def focus_areas():
    """Teaching focus-areas diagnostics for the current SSS3 cohort: a ranked list
    of subjects (with the evidence behind each) that need attention before the real
    exams, drawn from the active session's mock JAMB / mock WAEC / real JAMB.

    Admins see the whole cohort across classes; a teacher sees only the classes they
    are form teacher of."""
    from utils.focus_areas import build_focus_report
    from utils.access_control import is_admin, is_teacher, get_teacher_profile
    from utils.branch_scope import viewing_branch_id

    branch_id = viewing_branch_id()
    if branch_id == -1:
        branch_id = None        # central / all-branches view

    report = build_focus_report(branch_id=branch_id)

    # Teacher scope: limit the per-class views and at-risk list to their own classes.
    teacher_classes = None
    if is_teacher() and not is_admin():
        from models import ClassArmAssignment, ClassArm
        labels = set()
        teacher = get_teacher_profile()
        for caa_id in (teacher.form_class_ids if teacher else set()):
            caa = db.session.get(ClassArmAssignment, caa_id)
            if caa and caa.school_class and caa.school_class.name == 'SSS3':
                arm = db.session.get(ClassArm, caa.arm_id)
                if arm:
                    labels.add(arm.name)
        teacher_classes = labels
        report = _scope_focus_to_classes(report, labels)

    return render_template('results/focus_areas.html',
        report=report, is_admin_view=is_admin(), teacher_classes=teacher_classes)


@results_bp.route('/predictions/waec-model', methods=['GET', 'POST'])
@admin_required
def waec_model_config():
    """Admin control for the WAEC grade-band forecaster: choose the engine
    (auto / prior / bins / model) and retrain the per-branch ordinal models once
    a new cohort's real results have been entered."""
    from models.models import SchoolSettings
    from models.waec_grade_predict import (
        SETTING_KEY, VALID_METHODS, active_setting, training_pairs,
        evaluate_subject, choose_method, train_models,
        MIN_PAIRS_BINS, MIN_PAIRS_MODEL,
    )
    from utils.branch_scope import viewing_branch_id

    branch_id = viewing_branch_id()
    if branch_id == -1:
        branch_id = None        # "all branches" view → pooled stats

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'save_method':
            # The engine setting is global (cohort-wide, all branches), so only a
            # central admin may change it — a branch admin must not flip it for
            # everyone. Retraining below stays branch-scoped and admin-only.
            from utils.branch_scope import is_central
            if not is_central():
                flash('Only a central administrator can change the forecast engine.', 'error')
                return redirect(url_for('results.waec_model_config'))
            method = request.form.get('method', 'auto')
            if method in VALID_METHODS:
                SchoolSettings.set(SETTING_KEY, method, 'string',
                                   'WAEC grade-band prediction engine')
                flash(f'WAEC forecast engine set to “{method}”.', 'success')
        elif action == 'retrain':
            summary = train_models(branch_id)
            trained = sum(1 for r in summary if r['trained'])
            flash(f'Retrained {trained} subject model(s); '
                  f'{len(summary) - trained} still below the data threshold.', 'info')
        return redirect(url_for('results.waec_model_config'))

    setting = active_setting()
    pairs_by_subject = training_pairs(branch_id)
    rows = []
    for subject, pairs in sorted(pairs_by_subject.items()):
        n = len(pairs)
        ev = evaluate_subject(pairs) if n >= MIN_PAIRS_MODEL else None
        rows.append({
            'subject': subject, 'n': n,
            'auto_engine': choose_method(n, ev, 'auto'),
            'rps_bins': (round(ev['rps_bins'], 4) if ev and ev.get('rps_bins') is not None else None),
            'rps_model': (round(ev['rps_model'], 4) if ev and ev.get('rps_model') is not None else None),
        })
    return render_template('results/waec_model_config.html',
        setting=setting, methods=VALID_METHODS, rows=rows,
        min_bins=MIN_PAIRS_BINS, min_model=MIN_PAIRS_MODEL,
        total_pairs=sum(r['n'] for r in rows))


@results_bp.route('/predictions/student/<int:student_id>')
@login_required  
def student_predictions(student_id):
    """Comprehensive predictions for a specific student"""
    from utils.exam_analytics import WAECJAMBCorrelation, MockJAMBAnalytics
    from models.mock_jamb import MockJAMBResult
    from models.mock_waec import MockWAECResult, MockWAECAnalytics
    from utils import exam_insights

    student = db.get_or_404(Student, student_id)
    require_branch_access(student.branch_id)

    mock_results = MockJAMBResult.query.filter_by(student_id=student_id).all()
    mock_waec_count = MockWAECResult.query.filter_by(student_id=student_id).count()

    # Headline: a mocks-driven admission-readiness verdict. WAEC is projected from
    # the student's Mock WAEC trajectory and JAMB from Mock JAMB — most students
    # have neither real result yet (JAMB is sat in 2nd term, WAEC in 3rd).
    readiness = exam_insights.admission_readiness(student)

    # The WAEC subject outlook is projected directly from the Mock WAEC sittings —
    # the most direct WAEC signal — not from Mock JAMB.
    waec_from_mock = None
    try:
        waec_from_mock = MockWAECAnalytics.subject_outlook(student_id)
    except Exception:
        pass

    # Calibrated grade-band forecast: a full probability distribution over A1–F9
    # per subject (prior → bins → trained model, auto-selected per subject as the
    # branch accumulates graduated cohorts).
    # These are optional display blocks — degrading to None keeps the page usable,
    # but log the failure so a real bug isn't invisible (was a silent `pass`).
    grade_forecast = None
    if mock_waec_count:
        try:
            from models.waec_grade_predict import predict_student
            grade_forecast = predict_student(student_id)
        except Exception:
            current_app.logger.exception('grade_forecast failed for student %s', student_id)

    jamb_prediction = None
    if mock_results:
        try:
            jamb_prediction = MockJAMBAnalytics.predict_real_jamb(student_id)
        except Exception:
            current_app.logger.exception('mock-JAMB prediction failed for student %s', student_id)

    waec_years = [y[0] for y in db.session.query(WAECResult.exam_year)
                  .filter_by(student_id=student_id).distinct().all()]
    jamb_from_waec = None
    if waec_years:
        try:
            jamb_from_waec = WAECJAMBCorrelation.predict_jamb_from_waec(student_id, waec_years[0])
        except Exception:
            current_app.logger.exception('JAMB-from-WAEC prediction failed for student %s', student_id)

    return render_template('results/student_predictions.html',
        student=student,
        readiness=readiness,
        waec_from_mock=waec_from_mock,
        grade_forecast=grade_forecast,
        jamb_prediction=jamb_prediction,
        jamb_from_waec=jamb_from_waec,
        waec_years=waec_years,
        has_mock_results=len(mock_results) > 0,
        has_any_mock=(len(mock_results) > 0 or mock_waec_count > 0),
        mock_count=len(mock_results),
        mock_waec_count=mock_waec_count,
    )


@results_bp.route('/api/predictions/<int:student_id>')
@login_required
def api_student_predictions(student_id):
    """API endpoint for student predictions"""
    require_branch_access(db.get_or_404(Student, student_id).branch_id)
    from utils.exam_analytics import WAECJAMBCorrelation, MockJAMBAnalytics
    
    waec_from_mock = WAECJAMBCorrelation.predict_waec_from_mock_jamb(student_id)
    jamb_prediction = MockJAMBAnalytics.predict_real_jamb(student_id)
    
    return jsonify({
        'student_id': student_id,
        'waec_prediction': waec_from_mock,
        'jamb_prediction': jamb_prediction
    })
