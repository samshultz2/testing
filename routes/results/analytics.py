"""results blueprint — analytics routes (split from the former routes/results.py)."""
from routes.results import *  # noqa: F401,F403
from utils.web_exports import csv_response


@results_bp.route('/')
@login_required
def index():
    """Results main page with overview"""
    waec_count = WAECResult.query.count()
    jamb_count = JAMBResult.query.count()
    
    waec_years = db.session.query(WAECResult.exam_year).distinct().order_by(WAECResult.exam_year.desc()).all()
    jamb_years = db.session.query(JAMBResult.exam_year).distinct().order_by(JAMBResult.exam_year.desc()).all()
    waec_years = [y[0] for y in waec_years]
    jamb_years = [y[0] for y in jamb_years]

    return _render({
        'page': 'index',
        'waec_count': waec_count, 'jamb_count': jamb_count,
        'waec_years': waec_years, 'jamb_years': jamb_years,
        'urls': {
            'waec_dashboard': url_for('results.waec_list'), 'add_waec': url_for('results.add_waec'),
            'jamb_dashboard': url_for('results.jamb_list'), 'add_jamb': url_for('results.add_jamb'),
            'export_waec': url_for('results.export_waec', year=waec_years[0]) if waec_years else '',
            'export_jamb': url_for('results.export_jamb', year=jamb_years[0]) if jamb_years else '',
        },
    })


# The fixed exam rules (not a per-school setting): WAEC candidates register 9
# subjects, JAMB (UTME) is always exactly 4.
WAEC_EXPECTED_SUBJECTS = 9
JAMB_EXPECTED_SUBJECTS = 4


def _subject_count_mismatches(students, count_fn, expected):
    """Students (from the SSS3/exam-candidate cohort) whose subject count for
    one exam isn't the expected fixed number — miscounted registrations that
    need a look before results start coming in. Sorted worst-first (furthest
    from the expected count), then by name."""
    out = [{'id': s.id, 'name': s.full_name, 'student_id': s.student_id, 'count': n,
            'edit_url': url_for('main.edit_student', student_id=s.id)}
           for s in students for n in [count_fn(s)] if n != expected]
    out.sort(key=lambda r: (-abs(r['count'] - expected), r['name'] or ''))
    return out


@results_bp.route('/subject-enrolment')
@login_required
def subject_enrolment():
    """Report: how many students are enrolled for each WAEC / JAMB subject."""
    only_sss3 = request.args.get('scope', 'sss3') != 'all'
    if only_sss3:
        students = get_sss3_students()
    else:
        students = scope_query(Student.query.filter_by(is_active=True), Student).order_by(Student.surname).all()

    waec_counts = {}
    jamb_counts = {}
    waec_enrolled = 0
    jamb_enrolled = 0
    for s in students:
        wl = s.waec_subject_list
        jl = s.jamb_subject_list
        if wl:
            waec_enrolled += 1
        if jl:
            jamb_enrolled += 1
        for subj in wl:
            waec_counts[subj] = waec_counts.get(subj, 0) + 1
        for subj in jl:
            jamb_counts[subj] = jamb_counts.get(subj, 0) + 1

    waec_rows = sorted(waec_counts.items(), key=lambda x: (-x[1], x[0]))
    jamb_rows = sorted(jamb_counts.items(), key=lambda x: (-x[1], x[0]))
    scope = 'sss3' if only_sss3 else 'all'

    def _rows(rows, enrolled, exam):
        return [{'subject': subj, 'count': cnt,
                 'pct': round(cnt / enrolled * 100) if enrolled else 0,
                 'url': url_for('results.subject_enrolment_detail', exam=exam, subject=subj, scope=scope)}
                for subj, cnt in rows]

    # Subject-count mismatches always check the SSS3/exam-candidate cohort —
    # the count that actually matters for WAEC/JAMB registration — regardless
    # of which scope tab the page itself is showing.
    sss3_students = students if only_sss3 else get_sss3_students()
    waec_mismatches = _subject_count_mismatches(
        sss3_students, lambda s: len(s.waec_subject_list), WAEC_EXPECTED_SUBJECTS)
    jamb_mismatches = _subject_count_mismatches(
        sss3_students, lambda s: len(s.jamb_subject_list), JAMB_EXPECTED_SUBJECTS)

    return _render({
        'page': 'subject_enrolment', 'only_sss3': only_sss3, 'student_count': len(students),
        'waec_enrolled': waec_enrolled, 'jamb_enrolled': jamb_enrolled,
        'waec_rows': _rows(waec_rows, waec_enrolled, 'waec'),
        'jamb_rows': _rows(jamb_rows, jamb_enrolled, 'jamb'),
        'sss3_count': len(sss3_students),
        'waec_expected': WAEC_EXPECTED_SUBJECTS, 'jamb_expected': JAMB_EXPECTED_SUBJECTS,
        'waec_mismatches': waec_mismatches, 'jamb_mismatches': jamb_mismatches,
        'urls': {'sss3': url_for('results.subject_enrolment', scope='sss3'),
                 'all': url_for('results.subject_enrolment', scope='all')},
    })


@results_bp.route('/student/<int:student_id>/report')
@login_required
def student_report(student_id):
    """A consolidated, print/PDF-ready exam report for one student."""
    from models.mock_jamb import MockJAMBResult, MockJAMBExam, MockJAMBAnalytics

    student = db.get_or_404(Student, student_id)
    require_branch_access(student.branch_id)
    from utils.access_control import teacher_form_student_ids
    tids = teacher_form_student_ids()
    if tids is not None and student.id not in tids:
        abort(403)
    pass_grades = set(AcademicAnalytics.PASS_GRADES)
    distinction_grades = set(AcademicAnalytics.DISTINCTION_GRADES)

    # WAEC grouped by year with summary counts.
    waec = student.waec_results.order_by(WAECResult.exam_year.desc(), WAECResult.subject).all()
    waec_by_year = {}
    for r in waec:
        y = waec_by_year.setdefault(r.exam_year, {'rows': [], 'credits': 0, 'distinctions': 0})
        y['rows'].append(r)
        if r.grade in pass_grades:
            y['credits'] += 1
        if r.grade in distinction_grades:
            y['distinctions'] += 1
    waec_years = sorted(waec_by_year.items(), reverse=True)

    # JAMB results (most recent first), with subject breakdown.
    jamb = student.jamb_results.order_by(JAMBResult.exam_year.desc()).all()
    jamb_list = []
    for r in jamb:
        subs = []
        for n, sc in [(r.subject1, r.subject1_score), (r.subject2, r.subject2_score),
                      (r.subject3, r.subject3_score), (r.subject4, r.subject4_score)]:
            if n:
                subs.append({'subject': n, 'score': sc or 0})
        jamb_list.append({'year': r.exam_year, 'total': r.total_score, 'subjects': subs,
                          'level': AcademicAnalytics._jamb_performance_level(r.total_score)})

    # Mock JAMB progression + prediction (active session).
    mock_rows = MockJAMBResult.query.filter_by(student_id=student_id).join(MockJAMBExam).order_by(
        MockJAMBExam.exam_number).all()
    mock_progress = [{'name': m.exam.display_name, 'date': m.exam.exam_date, 'score': m.total_score}
                     for m in mock_rows]
    prediction = None
    active_session = get_active_session()
    if active_session:
        prediction = MockJAMBAnalytics.predict_real_jamb(student_id, active_session.id)

    from utils.admission import assess_admission
    admission = assess_admission(student)

    # Forward-looking readiness from the mock trajectory (actionable before the
    # real exams), plus the intended JAMB-combination check. The mock-based
    # prediction is corrected by the historical mock->real bias (cached).
    from utils import exam_insights, exam_trends
    bias = exam_insights.get_jamb_bias()
    if prediction:
        adj, applied = exam_insights.calibrate_jamb(prediction.get('predicted_score'), bias)
        if applied is not None:
            prediction['raw_score'] = prediction.get('predicted_score')
            prediction['predicted_score'] = adj
            prediction['calibrated_by'] = applied
    readiness = exam_insights.admission_readiness(
        student, active_session.id if active_session else None, calibration=bias)
    jamb_combo = exam_insights.jamb_subject_combo_check(student)
    # Difficulty-adjusted standing among peers (z-score / percentile per sitting).
    standing = exam_trends.standardized_mock_jamb_progress(
        student_id, active_session.id if active_session else None)

    # University aspiration: the student's OWN chosen-course verdict (gap to their
    # target + missing subjects) and the courses they're projected competitive
    # for. Reuses the readiness we already computed above — no recompute.
    sid = active_session.id if active_session else None
    aspiration = recommendations = subject_diag = None
    try:
        from utils.aspiration import (course_eligibility, recommend_courses,
                                       course_subject_diagnosis, ELIGIBILITY_LABELS)
        aspiration = course_eligibility(student, sid, readiness=readiness)
        if aspiration:
            aspiration['status_label'] = ELIGIBILITY_LABELS.get(aspiration.get('status'), aspiration.get('status'))
        recommendations = recommend_courses(student, sid, limit=8)
        # Attribute the target gap to specific course-relevant subjects.
        subject_diag = course_subject_diagnosis(student, sid)
    except Exception:
        aspiration = recommendations = subject_diag = None

    return render_template('results/student_report.html',
        student=student,
        waec_years=waec_years,
        jamb_list=jamb_list,
        mock_progress=mock_progress,
        prediction=prediction,
        admission=admission,
        readiness=readiness,
        jamb_combo=jamb_combo,
        standing=standing,
        aspiration=aspiration,
        recommendations=recommendations,
        subject_diag=subject_diag,
        generated=_date.today()
    )


@results_bp.route('/readiness')
@login_required
def readiness():
    """Actionable exam-readiness checklist for the SSS3 cohort."""
    students = get_sss3_students()
    total = len(students)

    # Readiness is judged from the MOCKS (Mock WAEC / Mock JAMB), since real JAMB
    # (2nd term) and WAEC (3rd term) don't exist yet for most of the cohort.
    no_stream, no_jamb, no_waec, no_jamb_subjects, no_waec_subjects = [], [], [], [], []
    below_target = []
    for s in students:
        if not s.stream:
            no_stream.append(s)
        if s.mock_jamb_results.count() == 0:
            no_jamb.append(s)
        if s.mock_waec_results.count() == 0:
            no_waec.append(s)
        if not s.jamb_subject_list:
            no_jamb_subjects.append(s)
        if not s.waec_subject_list:
            no_waec_subjects.append(s)
        if s.jamb_target:
            mocks = [m.total_score for m in s.mock_jamb_results.all()]
            best = max(mocks) if mocks else 0
            if best < s.jamb_target:
                below_target.append(s)

    groups = [
        {'key': 'no_jamb', 'title': 'No Mock JAMB result yet', 'icon': 'fa-file-contract', 'students': no_jamb},
        {'key': 'no_waec', 'title': 'No Mock WAEC result yet', 'icon': 'fa-file-alt', 'students': no_waec},
        {'key': 'below_target', 'title': 'Mock JAMB below their target', 'icon': 'fa-bullseye', 'students': below_target},
        {'key': 'no_stream', 'title': 'No stream / track set', 'icon': 'fa-route', 'students': no_stream},
        {'key': 'no_jamb_subjects', 'title': 'No JAMB subjects on profile', 'icon': 'fa-list', 'students': no_jamb_subjects},
        {'key': 'no_waec_subjects', 'title': 'No WAEC subjects on profile', 'icon': 'fa-list-check', 'students': no_waec_subjects},
    ]
    ready = total - len({s.id for g in groups for s in g['students']})

    def _action(key, sid):
        if key == 'no_jamb':
            return {'label': 'Mock JAMB', 'url': url_for('mock_jamb.index')}
        if key == 'no_waec':
            return {'label': 'Mock WAEC', 'url': url_for('mock_waec.index')}
        if key == 'no_jamb_subjects':
            return {'label': 'JAMB subjects', 'url': url_for('main.edit_student', student_id=sid)}
        if key == 'no_waec_subjects':
            return {'label': 'WAEC subjects', 'url': url_for('main.edit_student', student_id=sid)}
        return {'label': 'Edit', 'url': url_for('main.edit_student', student_id=sid)}

    return _render({
        'page': 'readiness', 'total': total, 'ready': ready,
        'groups': [{'key': g['key'], 'title': g['title'], 'icon': g['icon'],
                    'students': [{'id': s.id, 'full_name': s.full_name, 'student_id': s.student_id,
                                  'action': _action(g['key'], s.id)} for s in g['students']]}
                   for g in groups],
    })


@results_bp.route('/admission-readiness')
@login_required
def readiness_funnel():
    """Cohort admission-readiness funnel: how many SSS3 students are projected to
    get 5 credits incl. English & Maths, clear the JAMB baseline, and clear both
    (admission-ready) — from actual results where available, else the mocks."""
    from utils import exam_insights
    session = get_active_session()
    students = get_sss3_students()
    bias = exam_insights.get_jamb_bias()      # historical mock->real correction (cached)
    funnel = exam_insights.cohort_readiness(
        students, session.id if session else None, calibration=bias)
    # Rows sorted worst-first so intervention candidates surface at the top.
    order = {'NOT_READY': 0, 'AT_RISK': 1, 'CONDITIONAL': 2, 'READY': 3, 'NO_DATA': 4}
    rows = sorted(funnel['rows'], key=lambda r: order.get(r['readiness']['status'], 9))
    return render_template('results/readiness_funnel.html',
                           funnel=funnel, rows=rows, active_session=session, bias=bias)


@results_bp.route('/analytics')
@login_required
def analytics_hub():
    """One-stop analytics hub: every WAEC/JAMB stat, correlation and projection."""
    waec_years = [y[0] for y in db.session.query(WAECResult.exam_year).distinct().all()]
    jamb_years = [y[0] for y in db.session.query(JAMBResult.exam_year).distinct().all()]
    years = sorted(set(waec_years + jamb_years), reverse=True)

    year = resolve_exam_year(request.args.get('year', type=int), years)
    # The live session's exam year is always the resolved default (even with
    # zero results yet) — make sure the Year dropdown actually offers it, so
    # it doesn't misleadingly show a past year "selected" while the page is
    # really showing the current one.
    if year and year not in years:
        years = sorted(set(years) | {year}, reverse=True)
    compare_year = request.args.get('compare', type=int)

    from utils.branch_scope import viewing_branch_id
    bid = viewing_branch_id()
    waec_stats = waec_school_stats(year, bid) if year else None
    jamb_stats = jamb_school_stats(year, bid) if year else None
    correlation = waec_jamb_correlation(year, bid) if year else None
    yoy = AcademicAnalytics.get_year_over_year_comparison(bid)

    # Gender breakdowns for the selected year.
    def gender_split(model):
        q = db.session.query(Student.gender, func.count(func.distinct(Student.id))).join(
            model, Student.id == model.student_id
        ).filter(model.exam_year == year)
        if bid is not None:
            q = q.filter(Student.branch_id == bid)
        rows = q.group_by(Student.gender).all()
        return {g or 'Unknown': c for g, c in rows}

    waec_gender = gender_split(WAECResult) if (year and waec_stats) else {}
    jamb_gender = gender_split(JAMBResult) if (year and jamb_stats) else {}

    # Gender-comparison breakdown: pass/distinction rates (WAEC) and mean score
    # / >=200 rate (JAMB) split by gender for the selected year.
    waec_gender_stats = []
    if year and waec_stats:
        _q = db.session.query(Student.gender, WAECResult.grade).join(
            WAECResult, Student.id == WAECResult.student_id
        ).filter(WAECResult.exam_year == year)
        if bid is not None:
            _q = _q.filter(Student.branch_id == bid)
        rows = _q.all()
        by_gender = defaultdict(list)
        for g, grade in rows:
            by_gender[g or 'Unknown'].append(grade)
        for g, grades in by_gender.items():
            total = len(grades)
            passes = sum(1 for x in grades if x in AcademicAnalytics.PASS_GRADES)
            dist = sum(1 for x in grades if x in AcademicAnalytics.DISTINCTION_GRADES)
            pts = [AcademicAnalytics.GRADE_POINTS.get(x, 9) for x in grades]
            waec_gender_stats.append({
                'gender': g,
                'entries': total,
                'pass_rate': round(passes / total * 100, 1) if total else 0,
                'distinction_rate': round(dist / total * 100, 1) if total else 0,
                'mean_points': round(sum(pts) / len(pts), 2) if pts else 0,
            })
        waec_gender_stats.sort(key=lambda x: x['gender'])

    jamb_gender_stats = []
    if year and jamb_stats:
        _q = db.session.query(Student.gender, JAMBResult.total_score).join(
            JAMBResult, Student.id == JAMBResult.student_id
        ).filter(JAMBResult.exam_year == year)
        if bid is not None:
            _q = _q.filter(Student.branch_id == bid)
        rows = _q.all()
        by_gender = defaultdict(list)
        for g, score in rows:
            by_gender[g or 'Unknown'].append(score)
        for g, scores in by_gender.items():
            total = len(scores)
            jamb_gender_stats.append({
                'gender': g,
                'candidates': total,
                'mean_score': round(sum(scores) / total, 1) if total else 0,
                'above_200': sum(1 for s in scores if s >= 200),
                'above_200_rate': round(sum(1 for s in scores if s >= 200) / total * 100, 1) if total else 0,
                'max_score': max(scores) if scores else 0,
            })
        jamb_gender_stats.sort(key=lambda x: x['gender'])

    # JAMB mean projection (simple linear fit) computed directly from JAMB years.
    projection = None
    jamb_means = []
    for jy in sorted(set(jamb_years)):
        rs = scope_by_student(JAMBResult.query.filter_by(exam_year=jy), JAMBResult).all()
        if rs:
            jamb_means.append({'year': jy, 'mean_score': round(sum(r.total_score for r in rs) / len(rs), 1)})
    if len(jamb_means) >= 2:
        xs = [t['year'] for t in jamb_means]
        ys = [t['mean_score'] for t in jamb_means]
        n = len(xs)
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        denom = sum((x - mean_x) ** 2 for x in xs)
        slope = (sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n)) / denom) if denom else 0
        next_year = max(xs) + 1
        projected = round(mean_y + slope * (next_year - mean_x), 1)
        projected = max(0, min(400, projected))
        projection = {
            'next_year': next_year,
            'projected_mean': projected,
            'direction': 'up' if slope > 0.5 else 'down' if slope < -0.5 else 'flat',
            'slope_per_year': round(slope, 1),
            'latest_mean': ys[-1],
        }

    # University-cutoff readiness (JAMB >= 200) for the selected year.
    cutoff = None
    if year and jamb_stats:
        total = jamb_stats['total_students']
        cutoff = {
            'eligible_200': jamb_stats['above_200'],
            'eligible_200_pct': round(jamb_stats['above_200'] / total * 100, 1) if total else 0,
            'competitive_250': jamb_stats['above_250'],
            'competitive_250_pct': round(jamb_stats['above_250'] / total * 100, 1) if total else 0,
            'elite_300': jamb_stats['above_300'],
            'elite_300_pct': round(jamb_stats['above_300'] / total * 100, 1) if total else 0,
        }

    # Class/arm comparison + internal-vs-JAMB correlation for the selected year.
    class_compare = []
    internal_corr = None

    # Resolve year_session once here so both the class_compare block and the
    # attendance/subject-gains blocks below can share it.
    from utils.helpers import session_for_exam_year
    from models import Term as _Term
    year_session = session_for_exam_year(year) if year else None
    year_terms = (_Term.query.filter_by(session_id=year_session.id).all()
                  if year_session else [])

    if year:
        arm_map = {}
        if year_terms:
            term_ids = [t.id for t in year_terms]
            enrs = StudentEnrollment.query.join(ClassArmAssignment).filter(
                ClassArmAssignment.term_id.in_(term_ids),
                StudentEnrollment.is_active == True
            ).all()
            for e in enrs:
                arm_map.setdefault(e.student_id, e.class_arm_assignment.display_name)

        jamb_by_arm = defaultdict(list)
        for r in scope_by_student(JAMBResult.query.filter_by(exam_year=year), JAMBResult).all():
            arm = arm_map.get(r.student_id)
            if arm:
                jamb_by_arm[arm].append(r.total_score)
        waec_by_arm = defaultdict(lambda: {'pass': 0, 'total': 0})
        for r in scope_by_student(WAECResult.query.filter_by(exam_year=year), WAECResult).all():
            arm = arm_map.get(r.student_id)
            if arm:
                waec_by_arm[arm]['total'] += 1
                if r.grade in AcademicAnalytics.PASS_GRADES:
                    waec_by_arm[arm]['pass'] += 1
        for arm in sorted(set(list(jamb_by_arm) + list(waec_by_arm))):
            js = jamb_by_arm.get(arm, [])
            w = waec_by_arm.get(arm, {'pass': 0, 'total': 0})
            class_compare.append({
                'arm': arm,
                'jamb_count': len(js),
                'jamb_mean': round(sum(js) / len(js), 1) if js else 0,
                'waec_pass_rate': round(w['pass'] / w['total'] * 100, 1) if w['total'] else 0,
                'waec_entries': w['total'],
            })

        pairs = []
        # Use TermSummary rows from the selected session's terms so the internal
        # performance data matches the session we're analysing, not today's live term.
        for r in scope_by_student(JAMBResult.query.filter_by(exam_year=year), JAMBResult).all():
            if year_terms:
                term_ids = [t.id for t in year_terms]
                ts = (TermSummary.query.filter(TermSummary.student_id == r.student_id,
                                               TermSummary.term_id.in_(term_ids))
                      .order_by(TermSummary.term_id.desc()).first())
            else:
                ts = (TermSummary.query.filter_by(student_id=r.student_id)
                      .order_by(TermSummary.term_id.desc()).first())
            if ts and ts.average_score is not None:
                pairs.append((ts.average_score, r.total_score))
        if len(pairs) >= 5:
            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]
            internal_corr = {
                'n': len(pairs),
                'r': round(AcademicAnalytics._pearson_correlation(xs, ys), 3),
                'mean_internal': round(sum(xs) / len(xs), 1),
                'mean_jamb': round(sum(ys) / len(ys), 1),
            }

    # Trends from data we capture but didn't previously analyse. Mock JAMB/WAEC
    # progression is single-session data — scope it to ``year_session`` (the
    # session implied by the selected ?year, already resolved above, active
    # session as fallback), not whatever session happens to be live today, so
    # viewing a past year's analytics shows that year's mock-exam progression
    # rather than always the current session's.
    from utils import exam_trends
    active_sess = get_active_session()
    if year_session is None:
        year_session = active_sess
        if year_session:
            year_terms = _Term.query.filter_by(session_id=year_session.id).all()

    mock_trend = _mock_jamb_trend(bid, year_session)
    mock_waec_trend = _mock_waec_trend(bid, year_session)
    at_risk = _at_risk_register(limit=25)

    # attendance × JAMB correlation — scoped to the cohort that sat exams in
    # the selected year, not the current active SSS3.
    from utils.helpers import get_sss3_students
    if year and year_session and year_terms:
        # StudentEnrollment/ClassArmAssignment are already module-level names
        # here (via `from routes.results import *` at the top of this file) —
        # a local re-import previously sat on this line, which makes Python
        # treat the name as local for the WHOLE function and breaks the
        # earlier, unrelated use of StudentEnrollment above (line ~394) with
        # UnboundLocalError, since that use runs before this line does.
        year_term_ids = [t.id for t in year_terms]
        cohort_sids = {e.student_id for e in (
            StudentEnrollment.query.join(ClassArmAssignment)
            .filter(ClassArmAssignment.term_id.in_(year_term_ids),
                    StudentEnrollment.is_active == True).all())}
        all_sss3 = get_sss3_students()  # returns a list
        cohort_list = [s for s in all_sss3 if s.id in cohort_sids] if cohort_sids else all_sss3
    else:
        cohort_list = get_sss3_students()

    # Executive Smart Insights — synthesise the above stats into a ranked,
    # actionable "what / why / do next" summary (pure, adds no queries).
    from utils import exam_intelligence
    insights = exam_intelligence.school_insights(
        year=year, waec_stats=waec_stats, jamb_stats=jamb_stats,
        correlation=correlation, projection=projection, cutoff=cutoff,
        class_compare=class_compare, internal_corr=internal_corr,
        at_risk=at_risk, mock_trend=mock_trend,
        waec_gender_stats=waec_gender_stats, jamb_gender_stats=jamb_gender_stats,
        urls={'readiness': url_for('results.readiness_funnel'),
              'at_risk': url_for('results.api_at_risk')})

    from utils import exam_subjects
    scorecard = exam_subjects.subject_scorecard(
        waec_stats, jamb_stats, sss3_subject_teachers()) if year else []

    from utils.exam_refresh import refreshed_at
    return render_template('results/analytics_hub.html',
        insights=insights,
        analytics_refreshed_at=refreshed_at(),
        subject_scorecard=scorecard,
        scorecard_summary=exam_subjects.scorecard_summary(scorecard),
        branch_compare=branch_comparison(year) if year else [],
        year_compare=year_comparison(year, compare_year, bid) if year else None,
        compare_year=compare_year,
        years=years,
        selected_year=year,
        jamb_subjects=exam_trends.jamb_subject_breakdown(bid, year),
        waec_subject_gains=exam_trends.mock_waec_subject_gains(
            year_session.id if year_session else (active_sess.id if active_sess else None)
        ) if year else {},
        attendance_corr=exam_trends.attendance_performance_correlation(cohort_list, 'jamb'),
        class_compare=class_compare,
        internal_corr=internal_corr,
        waec_stats=waec_stats,
        jamb_stats=jamb_stats,
        correlation=correlation,
        yoy=yoy,
        waec_gender=waec_gender,
        jamb_gender=jamb_gender,
        waec_gender_stats=waec_gender_stats,
        jamb_gender_stats=jamb_gender_stats,
        projection=projection,
        cutoff=cutoff,
        at_risk=at_risk,
        mock_trend=mock_trend,
        mock_waec_trend=mock_waec_trend,
        recompute_url=url_for('results.recompute_analytics'),
    )


@results_bp.route('/analytics/by-class')
@login_required
def analytics_by_class():
    """External-exam performance rolled up to the class-arm level for a year —
    cohort-aware (maps each candidate to their latest senior-class arm)."""
    from utils.exam_class_league import exam_class_league
    from utils.branch_scope import viewing_branch_id
    waec_years = [y[0] for y in db.session.query(WAECResult.exam_year).distinct().all()]
    jamb_years = [y[0] for y in db.session.query(JAMBResult.exam_year).distinct().all()]
    years = sorted(set(waec_years + jamb_years), reverse=True)
    year = resolve_exam_year(request.args.get('year', type=int), years)
    data = exam_class_league(year, viewing_branch_id()) if year else None
    return render_template('results/analytics_by_class.html',
                           data=data, years=years, selected_year=year)


@results_bp.route('/analytics/trends')
@login_required
def analytics_trends():
    """Cross-year external-exam trends: how the WAEC 5-credits-incl-core / credit
    / F9 rates and the JAMB average & ≥200 rate move across every year on record.
    Branch-scoped to the branch being viewed."""
    from utils.branch_scope import viewing_branch_id
    bid = viewing_branch_id()
    waec = AcademicAnalytics.get_waec_multiyear_trends(bid)
    jamb = AcademicAnalytics.get_jamb_multiyear_trends(bid)
    subject_trends = AcademicAnalytics.get_waec_subject_trends(bid)

    def _delta(points, key):
        """Latest value, the change from the prior year, and the best year on
        record for one series metric — the headline 'insights' derived from the
        multi-year points."""
        if not points:
            return None
        latest = points[-1]
        prev = points[-2] if len(points) >= 2 else None
        best = max(points, key=lambda p: p.get(key, 0))
        return {
            'latest': latest.get(key), 'year': latest.get('year'),
            'delta': (round(latest.get(key, 0) - prev.get(key, 0), 1) if prev else None),
            'prev_year': prev.get('year') if prev else None,
            'best': best.get(key), 'best_year': best.get('year'),
        }

    insights = {
        'waec_core': _delta(waec['points'], 'with_5_incl_core_pct'),
        'waec_credit': _delta(waec['points'], 'credit_rate'),
        'waec_f9': _delta(waec['points'], 'f9_rate'),
        'jamb_avg': _delta(jamb['points'], 'avg_score'),
        'jamb_200': _delta(jamb['points'], 'above_200_pct'),
    }
    top_movers = subject_trends['movers'][:5]
    bottom_movers = list(reversed(subject_trends['movers'][-5:])) if subject_trends['movers'] else []
    return render_template('results/analytics_trends.html', waec=waec, jamb=jamb,
                           insights=insights, subject_trends=subject_trends,
                           top_movers=top_movers, bottom_movers=bottom_movers)


@results_bp.route('/analytics/watchlist')
@login_required
def at_risk_watchlist():
    """Live at-risk watchlist: SSS3 candidates projected off track for admission
    (from mock signals), grouped by class arm. Works before the risk engine runs."""
    from utils.at_risk_live import live_at_risk
    from utils.branch_scope import viewing_branch_id
    data = live_at_risk(branch_id=viewing_branch_id())
    return render_template('results/at_risk_watchlist.html', data=data,
                           action_plan_url='results.student_action_plan')


@results_bp.route('/analytics/aspirations')
@login_required
def aspiration_hub():
    """University-aspiration hub: target coverage, course-eligibility mix,
    most-wanted universities/courses, a JAMB subject-mismatch fix list, and the
    admission funnel with conversion. Projected live from mock signals."""
    from utils.aspiration_analytics import aspiration_overview
    from utils.branch_scope import viewing_branch_id
    data = aspiration_overview(branch_id=viewing_branch_id())
    return render_template('results/aspiration_hub.html', data=data)


@results_bp.route('/analytics/by-class/export')
@login_required
def analytics_by_class_export():
    """Export the class-arm external-exam league (Excel)."""
    from utils.exam_class_league import exam_class_league
    from utils.branch_scope import viewing_branch_id
    from utils.web_exports import xlsx_response
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    year = request.args.get('year', type=int)
    if not year:
        flash('Select a year first.', 'error')
        return redirect(url_for('results.analytics_by_class'))
    data = exam_class_league(year, viewing_branch_id())
    if not data or data['meta'].get('insufficient'):
        flash('No external results to group by class for that year.', 'warning')
        return redirect(url_for('results.analytics_by_class', year=year))
    wb = Workbook(); ws = wb.active; ws.title = f'By class {year}'
    head = ['Class arm', 'Students', 'JAMB candidates', 'JAMB mean', 'JAMB ≥ cutoff %',
            'WAEC students', 'Credit rate %', 'Distinction rate %', '5 credits incl. core %']
    ws.append(head)
    for c in ws[1]:
        c.fill = PatternFill('solid', fgColor='0D6A4E'); c.font = Font(bold=True, color='FFFFFF')
        c.alignment = Alignment(horizontal='center')
    for u in data['units']:
        ws.append([u['label'], u['students'], u['jamb_candidates'], u['jamb_mean'],
                   u['jamb_above_rate'], u['waec_students'], u['credit_rate'],
                   u['distinction_rate'], u['five_core_rate']])
    for col in ws.columns:
        w = max((len(str(c.value)) if c.value is not None else 0) for c in col) + 2
        ws.column_dimensions[col[0].column_letter].width = min(max(w, 12), 40)
    return xlsx_response(wb, f'exam_by_class_{year}.xlsx')


@results_bp.route('/analytics/export')
@login_required
def analytics_export():
    """Export the analytics hub for a year to a multi-sheet Excel workbook."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from io import BytesIO

    year = request.args.get('year', type=int)
    if not year:
        flash('Select a year to export.', 'error')
        return redirect(url_for('results.analytics_hub'))

    bid = viewing_branch_id()
    waec_stats = AcademicAnalytics.get_waec_school_statistics(year, bid)
    jamb_stats = AcademicAnalytics.get_jamb_school_statistics(year, bid)
    correlation = AcademicAnalytics.calculate_waec_jamb_correlation(year, bid)

    wb = Workbook()
    head_font = Font(bold=True, color='FFFFFF')
    head_fill = PatternFill(start_color='1a5f4a', end_color='1a5f4a', fill_type='solid')
    title_font = Font(bold=True, size=13)

    def style_header(ws, row=1):
        for cell in ws[row]:
            cell.font = head_font
            cell.fill = head_fill
            cell.alignment = Alignment(horizontal='center')

    # --- Overview sheet ---
    ws = wb.active
    ws.title = 'Overview'
    ws['A1'] = f'Exam Analytics — {year}'
    ws['A1'].font = title_font
    r = 3
    ws.cell(row=r, column=1, value='JAMB'); ws.cell(row=r, column=1).font = Font(bold=True); r += 1
    if jamb_stats:
        for label, key in [('Candidates', 'total_students'), ('Mean', 'mean_score'),
                           ('Median', 'median_score'), ('Highest', 'max_score'),
                           ('Lowest', 'min_score'), ('Std Dev', 'std_deviation'),
                           ('>=200', 'above_200'), ('>=250', 'above_250'), ('>=300', 'above_300')]:
            ws.cell(row=r, column=1, value=label); ws.cell(row=r, column=2, value=jamb_stats[key]); r += 1
    else:
        ws.cell(row=r, column=1, value='No JAMB data'); r += 1
    r += 1
    ws.cell(row=r, column=1, value='WAEC'); ws.cell(row=r, column=1).font = Font(bold=True); r += 1
    if waec_stats:
        for label, key in [('Students', 'unique_students'), ('Subject Entries', 'total_results'),
                           ('Pass Rate %', 'overall_pass_rate'), ('Distinction Rate %', 'overall_distinction_rate')]:
            ws.cell(row=r, column=1, value=label); ws.cell(row=r, column=2, value=waec_stats[key]); r += 1
    else:
        ws.cell(row=r, column=1, value='No WAEC data'); r += 1
    r += 1
    ws.cell(row=r, column=1, value='WAEC↔JAMB Correlation'); ws.cell(row=r, column=1).font = Font(bold=True); r += 1
    if correlation and not correlation.get('error'):
        for label, key in [('Pearson r', 'correlation_coefficient'), ('Predictive Power', 'predictive_power'),
                           ('Paired Students', 'sample_size')]:
            ws.cell(row=r, column=1, value=label); ws.cell(row=r, column=2, value=correlation[key]); r += 1
    else:
        ws.cell(row=r, column=1, value='Insufficient paired data'); r += 1
    ws.column_dimensions['A'].width = 22
    ws.column_dimensions['B'].width = 16

    # --- JAMB subjects ---
    if jamb_stats and jamb_stats['subject_analysis']:
        ws = wb.create_sheet('JAMB Subjects')
        ws.append(['Subject', 'Count', 'Mean', 'Max', 'Min', '>=50', '>=70'])
        style_header(ws)
        for s in jamb_stats['subject_analysis']:
            ws.append([s['subject'], s['count'], s['mean_score'], s['max_score'], s['min_score'], s['above_50'], s['above_70']])
        ws.column_dimensions['A'].width = 24

    # --- JAMB top 10 ---
    if jamb_stats and jamb_stats['top_10']:
        ws = wb.create_sheet('JAMB Top 10')
        ws.append(['Rank', 'Student', 'Score'])
        style_header(ws)
        for i, t in enumerate(jamb_stats['top_10'], 1):
            ws.append([i, t['student_name'], t['score']])
        ws.column_dimensions['B'].width = 28

    # --- WAEC subjects ---
    if waec_stats and waec_stats['subject_analysis']:
        ws = wb.create_sheet('WAEC Subjects')
        ws.append(['Subject', 'Entries', 'A1 %', 'Pass %', 'Below credit % (D7–F9)', 'Fail % (F9)'])
        style_header(ws)
        for s in sorted(waec_stats['subject_analysis'], key=lambda x: x['pass_rate'], reverse=True):
            ws.append([s['subject'], s['total_entries'], s['a1_rate'], s['pass_rate'],
                       s.get('below_credit_rate', 0), s['fail_rate']])
        ws.column_dimensions['A'].width = 24

    return xlsx_response(wb, f'exam_analytics_{year}.xlsx')


def _cutoff_from_jamb(jamb_stats):
    """University-readiness cut-off summary from JAMB school stats (mirrors the
    hub's inline computation), or None."""
    if not jamb_stats:
        return None
    total = jamb_stats['total_students']
    pct = lambda n: round(n / total * 100, 1) if total else 0
    return {'eligible_200': jamb_stats['above_200'], 'eligible_200_pct': pct(jamb_stats['above_200']),
            'competitive_250': jamb_stats['above_250'], 'competitive_250_pct': pct(jamb_stats['above_250']),
            'elite_300': jamb_stats['above_300'], 'elite_300_pct': pct(jamb_stats['above_300'])}


def _report_bundle(year, bid):
    """Shared stats + Smart Insights for the CSV / board-pack exports. Uses the
    cached school-stat wrappers so an export right after viewing the hub is free."""
    waec_stats = waec_school_stats(year, bid)
    jamb_stats = jamb_school_stats(year, bid)
    correlation = waec_jamb_correlation(year, bid)
    cutoff = _cutoff_from_jamb(jamb_stats)
    from utils import exam_intelligence
    insights = exam_intelligence.school_insights(
        year=year, waec_stats=waec_stats, jamb_stats=jamb_stats,
        correlation=correlation, cutoff=cutoff, at_risk=_at_risk_register(limit=25),
        urls={'readiness': url_for('results.readiness_funnel')})
    return waec_stats, jamb_stats, correlation, cutoff, insights


@results_bp.route('/analytics/export.csv')
@login_required
def analytics_export_csv():
    """Flat CSV of the year's key WAEC/JAMB stats + correlation (formula-guarded)."""
    import csv
    from io import StringIO
    from utils.web_exports import formula_guard as fg

    year = request.args.get('year', type=int)
    if not year:
        flash('Select a year to export.', 'error')
        return redirect(url_for('results.analytics_hub'))
    bid = viewing_branch_id()
    waec_stats, jamb_stats, correlation, cutoff, insights = _report_bundle(year, bid)

    out = StringIO()
    w = csv.writer(out)
    w.writerow(['Section', 'Metric', 'Value'])
    if jamb_stats:
        for label, key in [('Candidates', 'total_students'), ('Mean', 'mean_score'),
                           ('Median', 'median_score'), ('Highest', 'max_score'),
                           ('Lowest', 'min_score'), ('Std deviation', 'std_deviation'),
                           ('>=200', 'above_200'), ('>=250', 'above_250'), ('>=300', 'above_300')]:
            w.writerow(['JAMB', label, jamb_stats[key]])
    if cutoff:
        for label, key in [('Admissible (>=200) %', 'eligible_200_pct'),
                           ('Competitive (>=250) %', 'competitive_250_pct'),
                           ('Elite (>=300) %', 'elite_300_pct')]:
            w.writerow(['University readiness', label, cutoff[key]])
    if waec_stats:
        for label, key in [('Students', 'unique_students'), ('Subject entries', 'total_results'),
                           ('Pass rate %', 'overall_pass_rate'), ('Distinction rate %', 'overall_distinction_rate')]:
            w.writerow(['WAEC', label, waec_stats[key]])
    if correlation and not correlation.get('error'):
        for label, key in [('Pearson r', 'correlation_coefficient'),
                           ('Predictive power', 'predictive_power'), ('Paired students', 'sample_size')]:
            w.writerow(['WAEC<->JAMB', label, correlation[key]])
    if jamb_stats and jamb_stats.get('subject_analysis'):
        for s in jamb_stats['subject_analysis']:
            w.writerow(['JAMB subject', fg(s['subject']), s['mean_score']])
    if waec_stats and waec_stats.get('subject_analysis'):
        for s in sorted(waec_stats['subject_analysis'], key=lambda x: x['pass_rate'], reverse=True):
            w.writerow(['WAEC subject pass %', fg(s['subject']), s['pass_rate']])
    for i in insights:
        w.writerow(['Insight (%s)' % i['level'], fg(i['title']), fg(i['detail'])])

    return csv_response(out.getvalue(), f'exam_analytics_{year}.csv')


@results_bp.route('/analytics/board-pack')
@login_required
def analytics_board_pack():
    """One-page executive board-pack PDF: KPIs + Smart Insights + key stats."""
    from utils.web_exports import pdf_response
    from utils.exam_board_pack import board_pack_pdf
    from utils.school import school_profile

    year = request.args.get('year', type=int)
    if not year:
        flash('Select a year to export.', 'error')
        return redirect(url_for('results.analytics_hub'))
    bid = viewing_branch_id()
    waec_stats, jamb_stats, correlation, cutoff, insights = _report_bundle(year, bid)
    if not (waec_stats or jamb_stats):
        flash(f'No exam data for {year}.', 'error')
        return redirect(url_for('results.analytics_hub', year=year))

    branch_label = None
    if bid is not None:
        from models import Branch
        b = db.session.get(Branch, bid)
        branch_label = b.name if b else None

    pdf = board_pack_pdf(
        year=year, school_name=school_profile()['name'], generated=_date.today().isoformat(),
        insights=insights, jamb_stats=jamb_stats, waec_stats=waec_stats,
        cutoff=cutoff, correlation=correlation, branch_label=branch_label)
    log_action('analytics.board_pack', detail=f'year={year}, branch={bid or "all"}')
    return pdf_response(pdf, f'exam_board_pack_{year}.pdf', inline=True)


@results_bp.route('/analytics/deck.pptx')
@login_required
def analytics_deck():
    """Editable PowerPoint deck of the year's external-exam performance, for
    administration / parent / board meetings."""
    from flask import Response
    from utils.exam_deck import build_deck
    from utils.school import school_profile

    year = request.args.get('year', type=int)
    if not year:
        flash('Select a year to build the presentation.', 'error')
        return redirect(url_for('results.analytics_hub'))
    bid = viewing_branch_id()
    waec_stats, jamb_stats, correlation, cutoff, insights = _report_bundle(year, bid)
    if not (waec_stats or jamb_stats):
        flash(f'No exam data for {year}.', 'error')
        return redirect(url_for('results.analytics_hub', year=year))

    branch_label = None
    if bid is not None:
        from models import Branch
        b = db.session.get(Branch, bid)
        branch_label = b.name if b else None

    data = build_deck(
        year=year, school_name=school_profile()['name'], generated=_date.today().isoformat(),
        branch_label=branch_label, waec_stats=waec_stats, jamb_stats=jamb_stats,
        cutoff=cutoff, correlation=correlation, insights=insights)
    log_action('analytics.deck', detail=f'year={year}, branch={bid or "all"}')
    resp = Response(data, mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation')
    resp.headers['Content-Disposition'] = f'attachment; filename="exam_results_{year}.pptx"'
    return resp


@results_bp.route('/subject-enrolment/<exam>/<path:subject>')
@login_required
def subject_enrolment_detail(exam, subject):
    """List the students enrolled for a particular WAEC/JAMB subject."""
    exam = 'jamb' if exam.lower() == 'jamb' else 'waec'
    only_sss3 = request.args.get('scope', 'sss3') != 'all'
    if only_sss3:
        students = get_sss3_students()
    else:
        students = scope_query(Student.query.filter_by(is_active=True), Student).order_by(Student.surname).all()

    matched = []
    for s in students:
        enrolled = s.jamb_subject_list if exam == 'jamb' else s.waec_subject_list
        if subject in enrolled:
            matched.append(s)
    matched.sort(key=lambda s: (s.surname or '', s.first_name or ''))

    return _render({
        'page': 'subject_enrolment_detail', 'exam': exam,
        'exam_label': 'JAMB' if exam == 'jamb' else 'WAEC',
        'subject': subject, 'only_sss3': only_sss3,
        'students': [{'id': s.id, 'full_name': s.full_name, 'student_id': s.student_id,
                      'gender': s.gender or '', 'is_graduated': bool(s.is_graduated),
                      'view_url': url_for('main.view_student', student_id=s.id)} for s in matched],
        'back_url': url_for('results.subject_enrolment', scope='sss3' if only_sss3 else 'all'),
    })


@results_bp.route('/api/yoy-trends')
@login_required
def api_yoy_trends():
    """Get year-over-year performance trends"""
    data = AcademicAnalytics.get_year_over_year_comparison(viewing_branch_id())
    return jsonify(data)


@results_bp.route('/api/student-risk/<int:student_id>')
@login_required
def api_student_risk(student_id):
    """Get risk assessment for a student"""
    require_branch_access(db.get_or_404(Student, student_id).branch_id)
    risk = AcademicAnalytics.calculate_student_risk_score(student_id)
    return jsonify(risk)


@results_bp.route('/api/at-risk')
@login_required
def api_at_risk():
    out = _at_risk_register()
    return jsonify({'count': len(out), 'students': out})


@results_bp.route('/analytics/recompute', methods=['POST'])
@admin_required
def recompute_analytics():
    """Backfill/refresh persisted analytics for all in-scope students (and the
    WAEC↔JAMB correlation for recent years). Use after first deploy or a bulk
    import, since per-student rows are otherwise only written on results changes."""
    from utils.exam_refresh import run_exam_analytics_refresh
    bid = viewing_branch_id()
    # When the async-jobs flag is on, enqueue the (potentially slow) recompute so
    # the request returns immediately; the scheduler tick runs it in the
    # background. Otherwise run it synchronously exactly as before.
    from utils.jobs import async_enabled, enqueue
    if async_enabled():
        job = enqueue('analytics_recompute', {'branch_id': bid}, branch_id=bid)
        log_action('analytics.recompute', detail=f'queued job #{job.id}, branch={bid or "all"}')
        return _ok('Recompute queued — it will run in the background.',
                   url_for('results.tasks'))
    # Shared with the daily background job: recompute the SSS3 cohort, backfill
    # correlation, warm the hub caches, and stamp the refresh time.
    summary = run_exam_analytics_refresh(current_app, warm=True, branch_id=bid)
    log_action('analytics.recompute', detail=f'{summary["students"]} student(s), branch={bid or "all"}')
    return _ok(f'Recomputed analytics for {summary["students"]} student(s).',
               url_for('results.analytics_hub'))


@results_bp.route('/tasks')
@login_required
def tasks():
    """Background task list (async jobs). Empty/graceful when the feature is off
    or the table hasn't been created yet."""
    jobs = []
    try:
        from models import BackgroundJob
        jobs = (BackgroundJob.query.order_by(BackgroundJob.id.desc()).limit(50).all())
    except Exception:
        db.session.rollback()
    from utils.jobs import async_enabled
    return render_template('results/tasks.html', jobs=jobs, async_on=async_enabled())


@results_bp.route('/tasks/<int:job_id>.json')
@login_required
def task_status(job_id):
    """Poll a single job's status (for the Tasks page)."""
    from models import BackgroundJob
    job = db.session.get(BackgroundJob, job_id)
    if not job:
        abort(404)
    return jsonify(job.as_dict())


@results_bp.route('/api/waec-jamb-correlation/<int:year>')
@login_required
def api_waec_jamb_correlation(year):
    """Get WAEC-JAMB correlation data"""
    correlation = AcademicAnalytics.calculate_waec_jamb_correlation(year, viewing_branch_id())
    return jsonify(correlation)


@results_bp.route('/api/top-performers/<int:year>')
@login_required
def api_top_performers(year):
    """Get top performing students"""
    waec_stats = AcademicAnalytics.get_waec_school_statistics(year, viewing_branch_id())
    
    from utils.branch_scope import scope_by_student
    from utils.access_control import teacher_form_student_ids
    _jq = scope_by_student(JAMBResult.query.filter_by(exam_year=year).options(
        joinedload(JAMBResult.student)), JAMBResult)
    _tids = teacher_form_student_ids()
    if _tids is not None:
        _jq = _jq.filter(JAMBResult.student_id.in_(_tids or [-1]))
    jamb_results = _jq.order_by(JAMBResult.total_score.desc()).limit(10).all()
    
    jamb_top = [{
        'student_id': r.student_id,
        'name': r.student.full_name,
        'score': r.total_score
    } for r in jamb_results]
    
    return jsonify({
        'waec_top': waec_stats['top_performers'] if waec_stats else [],
        'jamb_top': jamb_top
    })


# =============================================================================
# WAEC BROADSHEET — the full grade matrix for an exam year (mirrors mock WAEC),
# viewable, printable (server PDF) and downloadable (PDF / Excel).
# =============================================================================

# Grade -> CSS badge tone, shared with the template.
_WAEC_GRADE_CLASS = {
    'A1': 'a1', 'B2': 'b', 'B3': 'b', 'C4': 'c', 'C5': 'c', 'C6': 'c',
    'D7': 'd', 'E8': 'e', 'F9': 'f',
}


def _waec_broadsheet_years():
    years = [y[0] for y in db.session.query(WAECResult.exam_year).distinct()
             .order_by(WAECResult.exam_year.desc()).all()]
    return years


def _waec_broadsheet_cached(year, branch_id):
    """The broadsheet, memoised in AnalyticsCache under the shared exam_hub
    namespace (so the existing bust/refresh invalidation covers it too)."""
    from routes.results import _cached_school_stats
    return _cached_school_stats(
        'waec_bs', year, branch_id,
        lambda: AcademicAnalytics.get_waec_broadsheet(year, branch_id))


def _broadsheet_etag(bs, year, branch_id, *extra):
    """A strong ETag derived from the broadsheet's actual grade matrix (every
    student's cells), so any grade edit changes it while an unchanged re-request
    is a cheap 304. ``extra`` carries output-shaping args (orientation, columns)."""
    import json
    from utils.http_cache import strong_etag
    fp = json.dumps([[r['student']['id'], r['cells']] for r in bs['rows']],
                    sort_keys=True, separators=(',', ':'))
    return strong_etag('waec_bs', year, branch_id, *extra, fp)


@results_bp.route('/waec/broadsheet')
@login_required
def waec_broadsheet():
    """On-screen WAEC broadsheet: grade matrix + per-subject and cohort summary."""
    years = _waec_broadsheet_years()
    year = resolve_exam_year(request.args.get('year', type=int), years)
    bs = _waec_broadsheet_cached(year, viewing_branch_id()) if year else None
    # {stream: [subjects students in that stream actually offered]} so the custom-
    # download modal can auto-tick a stream's subjects when the stream is picked.
    stream_subjects = {}
    if bs and bs.get('rows'):
        for r in bs['rows']:
            st = (r['student'].get('stream') or '').strip()
            if not st:
                continue
            present = stream_subjects.setdefault(st, set())
            for subj in bs['subjects']:
                if r['cells'].get(subj):
                    present.add(subj)
        stream_subjects = {k: sorted(v) for k, v in stream_subjects.items()}
    return render_template('results/waec_broadsheet.html', bs=bs, selected_year=year,
                           years=years, grade_classes=_WAEC_GRADE_CLASS,
                           stream_subjects=stream_subjects)


@results_bp.route('/waec/broadsheet.pdf')
@login_required
@rate_limited('export', max_requests=40, window_minutes=10)
def waec_broadsheet_pdf():
    """Server-side WAEC broadsheet PDF. Previews inline; ?download=1 to save."""
    from flask import send_file
    from utils.school import school_profile, logo_path
    years = _waec_broadsheet_years()
    year = resolve_exam_year(request.args.get('year', type=int), years)
    bs = _waec_broadsheet_cached(year, viewing_branch_id()) if year else None
    if not bs or not bs['rows']:
        flash('No WAEC results recorded for that year.', 'warning')
        return redirect(url_for('results.waec_broadsheet', year=year))
    per = request.args.get('cols', default=0, type=int)
    orient = request.args.get('orient', 'landscape')
    # Cheap 304 when the browser already holds this exact broadsheet frame.
    from utils.http_cache import if_none_match, stamp
    etag = _broadsheet_etag(bs, year, viewing_branch_id(), 'pdf', per, orient)
    not_modified = if_none_match(etag)
    if not_modified is not None:
        return not_modified
    from utils.waec_broadsheet_pdf import waec_broadsheet_pdf as _mk
    school = dict(school_profile() or {})
    school.setdefault('logo_path', logo_path())
    buf = _mk(bs, year, school, opts={'title': False},
              per=(per if per and per > 0 else 0), orient=orient)
    name = f'waec_broadsheet_{year}.pdf'
    resp = send_file(buf, mimetype='application/pdf',
                     as_attachment=request.args.get('download') == '1', download_name=name)
    return stamp(resp, etag)


@results_bp.route('/waec/broadsheet/export')
@login_required
@rate_limited('export', max_requests=40, window_minutes=10)
def waec_broadsheet_export():
    """Wide WAEC broadsheet workbook: a column per subject (grade), with the
    per-subject offered/passed/failed/average-grade rows beneath."""
    from openpyxl import Workbook
    years = _waec_broadsheet_years()
    year = resolve_exam_year(request.args.get('year', type=int), years)
    bs = _waec_broadsheet_cached(year, viewing_branch_id()) if year else None
    if not bs or not bs['rows']:
        flash('No WAEC results recorded for that year.', 'warning')
        return redirect(url_for('results.waec_broadsheet', year=year))
    from utils.http_cache import if_none_match
    etag = _broadsheet_etag(bs, year, viewing_branch_id(), 'xlsx')
    not_modified = if_none_match(etag)
    if not_modified is not None:
        return not_modified
    subjects = bs['subjects']

    wb = Workbook()
    ws = wb.active
    ws.title = f'WAEC {year}'
    ws.append(['S/N', 'Student'] + subjects + ['Credits', 'Avg grade'])
    for i, row in enumerate(bs['rows'], 1):
        line = [i, row['student']['full_name']]
        line += [row['cells'].get(subj, '') for subj in subjects]
        line += [row['credits'], row['avg_grade']]
        ws.append(line)

    ws.append([])
    ss = bs['subject_summary']
    def _summary_row(label, fn):
        ws.append(['', label] + [fn(ss[s]) for s in subjects] + ['', ''])
    _summary_row('No. offered', lambda d: d['offered'])
    _summary_row('No. passed (C6+)', lambda d: d['passed'])
    _summary_row('No. failed', lambda d: d['failed'])
    _summary_row('Average grade', lambda d: d['avg_grade'])

    from utils.http_cache import stamp
    return stamp(xlsx_response(wb, f'waec_broadsheet_{year}.xlsx'), etag)


@results_bp.route('/waec/broadsheet/download')
@login_required
@rate_limited('export', max_requests=40, window_minutes=10)
def waec_broadsheet_download():
    """Content-selectable WAEC broadsheet download: pick the streams (Science /
    Arts / Commercial) and the subjects to include, and the format
    (pdf | image | excel | csv). Powers the broadsheet's "Custom download" modal.
    """
    from flask import Response
    years = _waec_broadsheet_years()
    year = resolve_exam_year(request.args.get('year', type=int), years)
    bs = _waec_broadsheet_cached(year, viewing_branch_id()) if year else None
    if not bs or not bs['rows']:
        flash('No WAEC results recorded for that year.', 'warning')
        return redirect(url_for('results.waec_broadsheet', year=year))

    all_subjects = bs['subjects']
    want_subj = [s.strip() for s in (request.args.get('subjects') or '').split(',') if s.strip()]
    subjects = [s for s in all_subjects if s in want_subj] or all_subjects
    want_streams = {s.strip().lower() for s in (request.args.get('streams') or '').split(',') if s.strip()}

    rows = bs['rows']
    if want_streams:
        rows = [r for r in rows if (r['student'].get('stream') or '').lower() in want_streams]
    if not rows:
        flash('No students match the selected streams for that year.', 'warning')
        return redirect(url_for('results.waec_broadsheet', year=year))

    stream_label = ', '.join(sorted(s.title() for s in want_streams)) if want_streams else 'All streams'
    subtitle = f'WAEC Broadsheet {year} · {stream_label} · {len(rows)} student(s)'
    # Optional custom heading typed by the user (e.g. "SSS3 SCIENCE MERIT LIST").
    title = (request.args.get('title') or '').strip() or f'WAEC Broadsheet {year}'
    from utils.school import logo_path as _logo_path, school_profile as _school_profile
    _lp = _logo_path()
    _sname = (_school_profile() or {}).get('name') or None

    fmt = (request.args.get('format') or 'pdf').lower()
    from utils import broadsheet_export as bx

    # Spreadsheet/CSV keep the full subject names (they aren't width-constrained).
    full_headers = ['S/N', 'Student'] + subjects + ['Credits', 'Avg grade']
    full_rows = []
    for i, r in enumerate(rows, 1):
        line = [str(i), r['student']['full_name']]
        line += [r['cells'].get(subj, '–') for subj in subjects]
        line += [str(r['credits']), r['avg_grade']]
        full_rows.append(line)

    if fmt in ('excel', 'xlsx'):
        wb = bx.combo_xlsx(full_headers, full_rows, title, subtitle)
        return xlsx_response(wb, f'waec_broadsheet_{year}.xlsx')
    if fmt == 'csv':
        import csv as _csv
        from io import StringIO
        buf = StringIO(); w = _csv.writer(buf); w.writerow(full_headers)
        for dr in full_rows:
            w.writerow(dr)
        return Response(buf.getvalue(), mimetype='text/csv', headers={
            'Content-Disposition': f'attachment; filename="waec_broadsheet_{year}.csv"'})

    # PDF / image: short subject codes + a legend, so a wide sheet fits A4 legibly.
    codes, legend = bx.abbreviate_subjects(subjects)
    headers = ['S/N', 'Student'] + codes + ['Cred', 'Avg']
    if fmt in ('image', 'png'):
        pages = bx.combo_png_pages(headers, full_rows, title, subtitle, legend=legend,
                                   logo_path=_lp, school_name=_sname)
        page = request.args.get('page', type=int) or 1
        page = max(1, min(page, len(pages)))
        suffix = '' if len(pages) == 1 else f'_p{page}'
        return Response(pages[page - 1], mimetype='image/png', headers={
            'Content-Disposition': f'attachment; filename="waec_broadsheet_{year}{suffix}.png"',
            'X-Total-Pages': str(len(pages)), 'Access-Control-Expose-Headers': 'X-Total-Pages'})
    data = bx.combo_pdf(headers, full_rows, title, subtitle, numeric_from=2, legend=legend,
                        logo_path=_lp, school_name=_sname)
    return Response(data, mimetype='application/pdf', headers={
        'Content-Disposition': f'attachment; filename="waec_broadsheet_{year}.pdf"'})


# =============================================================================
# SUBJECT / BRANCH GRADE BREAKDOWN — a printed grade-analysis-sheet report:
# per subject, per branch, the percentage of candidates in each grade (WAEC /
# Mock WAEC) or score band (JAMB / Mock JAMB has no grades — 0-100 per
# subject), plus an overall summary by branch. Independent per exam kind.
# =============================================================================

# JAMB (& Mock JAMB) per-subject score bands — the JAMB-equivalent of WAEC's
# nine A1-F9 grade columns, since JAMB has no grading scale (raw 0-100/subject).
_JAMB_SCORE_BANDS = ['90-100', '80-89', '70-79', '60-69', '50-59', '40-49', '30-39', '20-29', '0-19']
_JAMB_PASS_BANDS = {'50-59', '60-69', '70-79', '80-89', '90-100'}
_WAEC_PASS_GRADES = {'A1', 'B2', 'B3', 'C4', 'C5', 'C6'}


def _jamb_score_band(score):
    if score is None:
        return None
    for lo, band in ((90, '90-100'), (80, '80-89'), (70, '70-79'), (60, '60-69'),
                     (50, '50-59'), (40, '40-49'), (30, '30-39'), (20, '20-29')):
        if score >= lo:
            return band
    return '0-19'


def _branch_grade_breakdown(entries, bands, pass_bands, uploaded=None):
    """``entries``: iterable of (subject, band, branch_name) — one per subject
    entry (a WAEC/Mock-WAEC result row, or one filled JAMB/Mock-JAMB subject
    slot). Aggregates into the per-subject-per-branch percentage table plus a
    per-branch overall summary, mirroring a school's printed grade-analysis
    sheet. A subject with zero entries at a branch is left out of that
    branch's per-subject row entirely (the template renders it "Not Offered").

    ``uploaded`` (optional): ``{(subject, branch_name): {'n': int, 'counts':
    {band: int}}}`` — a branch's own summary sheet, imported via OCR/paste
    instead of per-student rows (see models.grade_distribution). When given
    for a (subject, branch) pair it REPLACES whatever ``entries`` computed for
    that exact pair, since it's the branch's own authoritative figure."""
    from collections import defaultdict, Counter
    subj_branch = defaultdict(lambda: defaultdict(Counter))
    subj_total = Counter()
    branch_all = defaultdict(Counter)
    branch_n = Counter()
    branches_seen = set()

    for subject, band, branch in entries:
        if not subject or band is None or not branch:
            continue
        branches_seen.add(branch)
        subj_branch[subject][branch][band] += 1
        subj_total[subject] += 1
        branch_all[branch][band] += 1
        branch_n[branch] += 1

    uploaded_pairs = set()
    if uploaded:
        for (subject, branch), agg in uploaded.items():
            if not subject or not branch or not agg.get('n'):
                continue
            uploaded_pairs.add((subject, branch))
            branches_seen.add(branch)
            old = subj_branch[subject].pop(branch, None)
            if old:
                subj_total[subject] -= sum(old.values())
                branch_n[branch] -= sum(old.values())
                for b, c in old.items():
                    branch_all[branch][b] -= c
            counts = Counter({b: c for b, c in agg['counts'].items() if b in bands})
            subj_branch[subject][branch] = counts
            subj_total[subject] += agg['n']
            branch_n[branch] += agg['n']
            for b, c in counts.items():
                branch_all[branch][b] += c

    subjects = [s for s, _ in subj_total.most_common()]
    branches = sorted(branches_seen)

    table = {}
    for subj in subjects:
        table[subj] = {}
        for br in branches:
            counter = subj_branch[subj].get(br)
            n = sum(counter.values()) if counter else 0
            if not n:
                table[subj][br] = None
            else:
                table[subj][br] = {'n': n, 'uploaded': (subj, br) in uploaded_pairs,
                                   'pct': {b: round(counter.get(b, 0) / n * 100, 1) for b in bands}}

    summary = {}
    for br in branches:
        n = branch_n[br]
        c = branch_all[br]
        pass_n = sum(c.get(b, 0) for b in pass_bands)
        summary[br] = {
            'n': n,
            'pct': {b: round(c.get(b, 0) / n * 100, 1) for b in bands} if n else {b: 0 for b in bands},
            'pass_n': pass_n,
            'pass_pct': round(pass_n / n * 100, 1) if n else 0,
        }

    return {'subjects': subjects, 'branches': branches, 'bands': bands,
            'table': table, 'summary': summary}


def _uploaded_distribution(branch_names, exam, bid, exam_year=None, mock_session_id=None, mock_exam_number=None):
    """Branch-supplied grade/score distributions for this exact (exam, period)
    — see models.grade_distribution.BranchGradeDistribution. Returns
    ``{(subject, branch_name): {'n': int, 'counts': {band: int}}}`` ready for
    ``_branch_grade_breakdown``'s ``uploaded=`` argument."""
    from models import BranchGradeDistribution
    q = BranchGradeDistribution.query.filter_by(exam=exam, exam_year=exam_year,
                                                mock_session_id=mock_session_id,
                                                mock_exam_number=mock_exam_number)
    if bid is not None:
        q = q.filter(BranchGradeDistribution.branch_id == bid)
    out = {}
    for row in q.all():
        br = branch_names.get(row.branch_id)
        if not br:
            continue
        out[(row.subject, br)] = {'n': row.candidates, 'counts': row.counts()}
    return out


def _pivot_jamb_entries(rows_with_branch):
    """``rows_with_branch``: iterable of (JAMBResult|MockJAMBResult, branch_name).
    Each result carries up to 4 (subject, score) slots — yield one
    (subject, band, branch) tuple per filled slot."""
    for r, branch in rows_with_branch:
        for i in range(1, 5):
            subj = getattr(r, f'subject{i}')
            score = getattr(r, f'subject{i}_score')
            if subj and score is not None:
                yield (subj, _jamb_score_band(score), branch)


def _load_grade_breakdown(exam):
    """Shared data-loader for the Subject-Wise Grade Breakdown report — used by
    both the on-screen page and its PDF/Word/Excel/PNG exports, so they can
    never drift apart. Returns a dict of everything the template/exporters need."""
    from models import Branch
    from utils.branch_scope import viewing_branch_id

    if exam not in ('waec', 'jamb', 'mock_waec', 'mock_jamb'):
        exam = 'waec'
    bid = viewing_branch_id()
    branch_names = {b.id: b.name for b in Branch.query.all()}

    result = None
    years = []
    mock_options = []
    selected_year = None
    selected_mock = None
    pass_label = 'Overall Credit Pass (A1–C6)' if exam in ('waec', 'mock_waec') else 'Overall ≥50 Rate'
    band_label = 'Grade' if exam in ('waec', 'mock_waec') else 'Score Band'
    exam_label = {'waec': 'WAEC', 'jamb': 'JAMB', 'mock_waec': 'Mock WAEC', 'mock_jamb': 'Mock JAMB'}[exam]
    period_label = None

    if exam in ('waec', 'jamb'):
        from models import BranchGradeDistribution
        Model = WAECResult if exam == 'waec' else JAMBResult
        yq = db.session.query(Model.exam_year).distinct()
        if bid is not None:
            yq = yq.join(Student, Model.student_id == Student.id).filter(Student.branch_id == bid)
        years = {y[0] for y in yq.all()}
        # Union in years covered only by an uploaded branch summary sheet (no
        # per-student rows at all) so the dropdown doesn't hide that period.
        uyq = db.session.query(BranchGradeDistribution.exam_year).filter_by(exam=exam).distinct()
        if bid is not None:
            uyq = uyq.filter(BranchGradeDistribution.branch_id == bid)
        years |= {y[0] for y in uyq.all() if y[0] is not None}
        years = sorted(years, reverse=True)
        selected_year = resolve_exam_year(request.args.get('year', type=int), years)
        period_label = f'Exam Year {selected_year}' if selected_year else None
        if selected_year:
            q = (db.session.query(Model, Student.branch_id)
                 .join(Student, Model.student_id == Student.id)
                 .filter(Model.exam_year == selected_year))
            if bid is not None:
                q = q.filter(Student.branch_id == bid)
            rows_with_branch = [(r, branch_names.get(br)) for r, br in q.all()]
            if exam == 'waec':
                entries = [(r.subject, r.grade, br) for r, br in rows_with_branch]
                bands, pass_bands = WAECResult.VALID_GRADES, _WAEC_PASS_GRADES
            else:
                entries = list(_pivot_jamb_entries(rows_with_branch))
                bands, pass_bands = _JAMB_SCORE_BANDS, _JAMB_PASS_BANDS
            uploaded = _uploaded_distribution(branch_names, exam, bid, exam_year=selected_year)
            result = _branch_grade_breakdown(entries, bands, pass_bands, uploaded=uploaded)
    else:
        from models import AcademicSession
        from models.mock_waec import MockWAECExam, MockWAECResult
        from models.mock_jamb import MockJAMBExam, MockJAMBResult
        ExamModel = MockWAECExam if exam == 'mock_waec' else MockJAMBExam
        ResultModel = MockWAECResult if exam == 'mock_waec' else MockJAMBResult

        from models import BranchGradeDistribution
        pq = db.session.query(ExamModel.session_id, ExamModel.exam_number)
        if bid is not None:
            pq = pq.filter(ExamModel.branch_id == bid)
        pairs = set(pq.distinct().all())
        # Union in sittings covered only by an uploaded branch summary sheet
        # (no per-student rows at all) so the dropdown doesn't hide them.
        uq = db.session.query(BranchGradeDistribution.mock_session_id, BranchGradeDistribution.mock_exam_number
                             ).filter_by(exam=exam)
        if bid is not None:
            uq = uq.filter(BranchGradeDistribution.branch_id == bid)
        pairs |= {p for p in uq.distinct().all() if p[0] is not None and p[1] is not None}
        sess_names = {s.id: s.name for s in AcademicSession.query.all()}
        mock_options = sorted(
            ({'session_id': sid, 'exam_number': num,
              'label': f"Mock {num} — {sess_names.get(sid, '?')}"} for sid, num in pairs),
            key=lambda o: (sess_names.get(o['session_id'], ''), o['exam_number']), reverse=True)

        mock_param = request.args.get('mock', '')
        if mock_param and '_' in mock_param:
            try:
                req_sid, req_num = (int(x) for x in mock_param.split('_', 1))
                selected_mock = next((o for o in mock_options
                                      if o['session_id'] == req_sid and o['exam_number'] == req_num), None)
            except ValueError:
                selected_mock = None
        if selected_mock is None and mock_options:
            active_session = get_active_session()
            active_sid = active_session.id if active_session else None
            selected_mock = next((o for o in mock_options if o['session_id'] == active_sid),
                                 mock_options[0])

        if selected_mock:
            period_label = selected_mock['label']
            exam_ids = [e.id for e in ExamModel.query.filter_by(
                session_id=selected_mock['session_id'], exam_number=selected_mock['exam_number']).all()]
            q = (db.session.query(ResultModel, Student.branch_id)
                 .join(Student, ResultModel.student_id == Student.id)
                 .filter(ResultModel.mock_exam_id.in_(exam_ids)))
            if bid is not None:
                q = q.filter(Student.branch_id == bid)
            rows_with_branch = [(r, branch_names.get(br)) for r, br in q.all()]
            if exam == 'mock_waec':
                entries = [(r.subject, r.grade, br) for r, br in rows_with_branch]
                bands, pass_bands = WAECResult.VALID_GRADES, _WAEC_PASS_GRADES
            else:
                entries = list(_pivot_jamb_entries(rows_with_branch))
                bands, pass_bands = _JAMB_SCORE_BANDS, _JAMB_PASS_BANDS
            uploaded = _uploaded_distribution(branch_names, exam, bid,
                                              mock_session_id=selected_mock['session_id'],
                                              mock_exam_number=selected_mock['exam_number'])
            result = _branch_grade_breakdown(entries, bands, pass_bands, uploaded=uploaded)

    return {'exam': exam, 'exam_label': exam_label, 'period_label': period_label,
           'result': result, 'years': years, 'selected_year': selected_year,
           'mock_options': mock_options, 'selected_mock': selected_mock,
           'pass_label': pass_label, 'band_label': band_label}


@results_bp.route('/subject-branch-breakdown')
@login_required
def subject_branch_breakdown():
    """Subject-wise performance & grade/score-band percentage breakdown, by
    branch — independently for WAEC, JAMB, Mock WAEC or Mock JAMB."""
    exam = request.args.get('exam', 'waec')
    data = _load_grade_breakdown(exam)
    return render_template('results/subject_branch_breakdown.html', **data)


@results_bp.route('/subject-branch-breakdown/export.<fmt>')
@login_required
@rate_limited('export', max_requests=40, window_minutes=10)
def subject_branch_breakdown_export(fmt):
    """Download the Grade Breakdown report as a PDF, Word doc, Excel workbook
    or an HD PNG (zipped if it spans multiple pages)."""
    import io
    from flask import send_file
    if fmt not in ('pdf', 'docx', 'xlsx', 'png'):
        abort(404)
    exam = request.args.get('exam', 'waec')
    data = _load_grade_breakdown(exam)
    if not data['result'] or not data['result']['subjects']:
        flash('No data to export yet.', 'warning')
        return redirect(url_for('results.subject_branch_breakdown', exam=data['exam']))

    from utils.school import school_profile
    profile = school_profile()
    period = data['period_label'] or ''
    meta = {'school_name': profile.get('name'), 'logo_path': profile.get('logo_path'),
           'subtitle': f"{data['exam_label']} — {period}" if period else data['exam_label']}
    fname_base = f"grade_breakdown_{data['exam']}_{(period or '').replace(' ', '_').replace('/', '-')}"

    if fmt == 'pdf':
        from utils.grade_breakdown_export import grade_breakdown_pdf
        buf = grade_breakdown_pdf(meta, data['result'], data['band_label'], data['pass_label'])
        return send_file(io.BytesIO(buf), mimetype='application/pdf',
                         as_attachment=True, download_name=f'{fname_base}.pdf')
    if fmt == 'docx':
        from utils.grade_breakdown_export import grade_breakdown_docx
        buf = grade_breakdown_docx(meta, data['result'], data['band_label'], data['pass_label'])
        return send_file(io.BytesIO(buf), mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                         as_attachment=True, download_name=f'{fname_base}.docx')
    if fmt == 'xlsx':
        from utils.grade_breakdown_export import grade_breakdown_xlsx
        wb = grade_breakdown_xlsx(meta, data['result'], data['band_label'], data['pass_label'])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True, download_name=f'{fname_base}.xlsx')
    from utils.grade_breakdown_export import grade_breakdown_image_export
    payload, mimetype, ext = grade_breakdown_image_export(meta, data['result'], data['band_label'], data['pass_label'])
    return send_file(io.BytesIO(payload), mimetype=mimetype,
                     as_attachment=True, download_name=f'{fname_base}.{ext}')


# =============================================================================
# BRANCH GRADE DISTRIBUTION IMPORT — for a branch that reports a subject-wise
# summary sheet (candidates sat + a count per grade/score-band) instead of
# entering individual student WAEC/JAMB results. Paste, file upload, or an
# AI-vision photo all funnel into the same review grid before saving — the
# source document itself is never stored, only the reviewed numbers.
# =============================================================================

def _grade_distribution_bands(exam):
    return WAECResult.VALID_GRADES if exam in ('waec', 'mock_waec') else _JAMB_SCORE_BANDS


def _grade_distribution_catalog(exam):
    from utils.exam_subject_config import get_config
    key = 'waec' if exam in ('waec', 'mock_waec') else 'jamb'
    return get_config()[key]['catalog'] or WAEC_SUBJECTS


@results_bp.route('/subject-branch-breakdown/import', methods=['GET', 'POST'])
@login_required
@rate_limited('ocr', max_requests=30, window_minutes=10)
def grade_distribution_import():
    """Step 1: pick the branch/period and paste/upload/scan the report. Never
    saves anything itself — always hands off to the review grid."""
    from models import Branch, AcademicSession
    from utils.branch_scope import viewing_branch_id
    from utils.grade_distribution_import import parse_pasted_table, build_distribution_rows
    from utils.broadsheet_import import parse_table

    exam = request.args.get('exam', 'waec')
    if exam not in ('waec', 'jamb', 'mock_waec', 'mock_jamb'):
        exam = 'waec'
    bands = _grade_distribution_bands(exam)
    band_label = 'Grade' if exam in ('waec', 'mock_waec') else 'Score Band'

    bid = viewing_branch_id()
    if bid is not None:
        branches = [b for b in [db.session.get(Branch, bid)] if b]
    else:
        branches = Branch.query.order_by(Branch.name).all()

    years = []
    mock_options = []
    if exam in ('waec', 'jamb'):
        Model = WAECResult if exam == 'waec' else JAMBResult
        years = sorted({y[0] for y in db.session.query(Model.exam_year).distinct().all()}, reverse=True)
        current_year = session_exam_year(get_active_session())
        if current_year and current_year not in years:
            years = sorted(set(years) | {current_year}, reverse=True)
    else:
        from models.mock_waec import MockWAECExam
        from models.mock_jamb import MockJAMBExam
        ExamModel = MockWAECExam if exam == 'mock_waec' else MockJAMBExam
        pairs = db.session.query(ExamModel.session_id, ExamModel.exam_number).distinct().all()
        sess_names = {s.id: s.name for s in AcademicSession.query.all()}
        mock_options = sorted(
            ({'session_id': sid, 'exam_number': num, 'label': f"Mock {num} — {sess_names.get(sid, '?')}"}
             for sid, num in pairs),
            key=lambda o: (sess_names.get(o['session_id'], ''), o['exam_number']), reverse=True)

    if request.method == 'POST':
        branch_id = request.form.get('branch_id', type=int)
        branch = db.session.get(Branch, branch_id) if branch_id else None
        if not branch or (bid is not None and branch.id != bid):
            flash('Select a valid branch.', 'error')
            return redirect(url_for('results.grade_distribution_import', exam=exam))

        method = request.form.get('method', 'paste')
        table = None
        if method == 'paste':
            text = (request.form.get('data') or '').strip()
            if not text:
                flash('Paste the report text first.', 'error')
                return redirect(url_for('results.grade_distribution_import', exam=exam))
            table = parse_pasted_table(text)
        elif method == 'file':
            file = request.files.get('file')
            if not file or not file.filename:
                flash('Choose a file to upload.', 'error')
                return redirect(url_for('results.grade_distribution_import', exam=exam))
            from utils.uploads import ext_ok
            if not ext_ok(file.filename, {'.csv', '.xlsx', '.xlsm', '.xls'}):
                flash('Please upload a CSV or Excel file.', 'error')
                return redirect(url_for('results.grade_distribution_import', exam=exam))
            table = parse_table(file.read(), file.filename)
        else:
            from utils.waec_ocr import vision_available, vision_extract_grade_distribution, last_vision_error
            file = request.files.get('photo')
            if not file or not file.filename:
                flash('Choose a photo to scan.', 'error')
                return redirect(url_for('results.grade_distribution_import', exam=exam))
            from utils.uploads import ext_ok, SCAN_EXTS
            if not ext_ok(file.filename, SCAN_EXTS):
                flash('Please upload an image.', 'error')
                return redirect(url_for('results.grade_distribution_import', exam=exam))
            if not vision_available():
                flash('AI vision OCR is not enabled on this server — paste the text or upload a file instead.', 'error')
                return redirect(url_for('results.grade_distribution_import', exam=exam))
            table = vision_extract_grade_distribution(file.read(), file.mimetype or 'image/png')
            if not table:
                flash(last_vision_error() or 'Could not read the photo — try pasting the text instead.', 'warning')
                return redirect(url_for('results.grade_distribution_import', exam=exam))

        if not table or not table.get('rows'):
            flash('No rows could be read from that input.', 'warning')
            return redirect(url_for('results.grade_distribution_import', exam=exam))

        catalog = _grade_distribution_catalog(exam)
        parsed_rows = build_distribution_rows(table['headers'], table['rows'], bands, subject_catalog=catalog)
        if not parsed_rows:
            flash('No subject rows could be read from that input — check the format and try again.', 'warning')
            return redirect(url_for('results.grade_distribution_import', exam=exam))

        period = {}
        if exam in ('waec', 'jamb'):
            period['exam_year'] = request.form.get('exam_year', type=int)
        else:
            mock_param = request.form.get('mock', '')
            if '_' in mock_param:
                try:
                    sid, num = mock_param.split('_', 1)
                    period['mock_session_id'] = int(sid)
                    period['mock_exam_number'] = int(num)
                except ValueError:
                    pass

        return render_template('results/grade_distribution_review.html',
            exam=exam, bands=bands, band_label=band_label, branch=branch,
            rows=parsed_rows, period=period, source=method, subjects=catalog)

    return render_template('results/grade_distribution_import.html',
        exam=exam, band_label=band_label, branches=branches, bid=bid,
        years=years, mock_options=mock_options,
        current_year=session_exam_year(get_active_session()) or _date.today().year)


@results_bp.route('/subject-branch-breakdown/import/save', methods=['POST'])
@login_required
def grade_distribution_import_save():
    """Step 2: commit the reviewed/edited grid — replaces whatever this branch
    had stored for this exact (exam, period), so re-importing a corrected
    sheet is just "do it again"."""
    from flask import session as flask_session
    from models import Branch, BranchGradeDistribution
    from utils.branch_scope import require_branch_access

    exam = request.form.get('exam', 'waec')
    if exam not in ('waec', 'jamb', 'mock_waec', 'mock_jamb'):
        exam = 'waec'
    bands = _grade_distribution_bands(exam)

    branch_id = request.form.get('branch_id', type=int)
    branch = db.session.get(Branch, branch_id) if branch_id else None
    if not branch:
        flash('Select a valid branch.', 'error')
        return redirect(url_for('results.grade_distribution_import', exam=exam))
    require_branch_access(branch.id)

    exam_year = request.form.get('exam_year', type=int) if exam in ('waec', 'jamb') else None
    mock_session_id = request.form.get('mock_session_id', type=int) if exam in ('mock_waec', 'mock_jamb') else None
    mock_exam_number = request.form.get('mock_exam_number', type=int) if exam in ('mock_waec', 'mock_jamb') else None
    if exam in ('waec', 'jamb') and not exam_year:
        flash('Select the exam year.', 'error')
        return redirect(url_for('results.grade_distribution_import', exam=exam))
    if exam in ('mock_waec', 'mock_jamb') and not (mock_session_id and mock_exam_number):
        flash('Select the mock sitting.', 'error')
        return redirect(url_for('results.grade_distribution_import', exam=exam))

    subjects = request.form.getlist('subject[]')
    candidates_list = request.form.getlist('candidates[]')
    new_rows = []
    for i, subj in enumerate(subjects):
        subj = (subj or '').strip()
        if not subj:
            continue
        try:
            candidates = int(candidates_list[i]) if i < len(candidates_list) and candidates_list[i] else 0
        except ValueError:
            candidates = 0
        counts = {}
        total = 0
        for b in bands:
            raw = (request.form.get(f'band_{i}_{b}') or '').strip()
            try:
                v = int(raw) if raw else 0
            except ValueError:
                v = 0
            counts[b] = v
            total += v
        if not candidates:
            candidates = total
        if not candidates and not total:
            continue
        row = BranchGradeDistribution(
            branch_id=branch.id, exam=exam, exam_year=exam_year,
            mock_session_id=mock_session_id, mock_exam_number=mock_exam_number,
            subject=subj, candidates=candidates,
            source=request.form.get('source', 'manual')[:10],
            imported_by=flask_session.get('user_id'))
        row.set_counts(counts)
        new_rows.append(row)

    if not new_rows:
        flash('No subject rows to save — check the values and try again.', 'warning')
        return redirect(url_for('results.grade_distribution_import', exam=exam))

    BranchGradeDistribution.query.filter_by(
        branch_id=branch.id, exam=exam, exam_year=exam_year,
        mock_session_id=mock_session_id, mock_exam_number=mock_exam_number
    ).delete(synchronize_session=False)
    db.session.add_all(new_rows)
    db.session.commit()
    log_action('results.grade_distribution_import', detail=f'{exam} {branch.name}', target=branch)
    flash(f'Saved {len(new_rows)} subject row(s) for {branch.name}.', 'success')

    redirect_kwargs = {'exam': exam}
    if exam_year:
        redirect_kwargs['year'] = exam_year
    elif mock_session_id and mock_exam_number:
        redirect_kwargs['mock'] = f'{mock_session_id}_{mock_exam_number}'
    return redirect(url_for('results.subject_branch_breakdown', **redirect_kwargs))
