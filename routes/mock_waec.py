"""
Mock WAEC Examination Routes

Full management of internal Mock WAEC exams (multiple per session), mirroring the
real WAEC section but marked out of 100 with auto-derived A1-F9 grades. Includes
single-student entry, a paste-and-preview bulk importer, per-student progression,
school analytics, Excel export, and live feeding of the analytics inference engine.
"""
import re
from datetime import datetime

from flask import (Blueprint, request, redirect, url_for, flash, render_template,
                   abort, send_file)
from openpyxl import Workbook

from models import db, Student, AcademicSession, SchoolSettings
from models.mock_waec import (MockWAECExam, MockWAECResult, MockWAECAnalytics,
                              waec_grade_from_score, PASS_GRADES)
from utils.helpers import (login_required, get_active_session, get_sss3_students,
                           WAEC_SUBJECTS, WAEC_GRADES, WAEC_DEFAULT_SUBJECTS,
                           STREAM_WAEC_SUBJECTS, student_subject_map)
from utils.access_control import admin_required
from utils.security import rate_limited
from utils.branch_scope import require_branch_access, branch_for_new, scope_query
from utils.csrf import csrf_protect
from utils.web_exports import xlsx_response
from utils.analytics_engine import recompute_student_safe
from utils.subject_match import canonical_subject

mock_waec_bp = Blueprint('mock_waec', __name__, url_prefix='/mock-waec')

# =============================================================================
# DASHBOARD
# =============================================================================

@mock_waec_bp.route('/')
@login_required
def index():
    """Mock WAEC dashboard: exams for the selected session + cohort comparison."""
    active_session = get_active_session()
    sessions = AcademicSession.query.order_by(AcademicSession.name.desc()).all()

    session_id = request.args.get('session_id', type=int)
    if not session_id and active_session:
        session_id = active_session.id

    # A derived SSS3-arm teacher sees the exams for entry, but only their arm's
    # counts and none of the cohort comparison.
    from utils.access_control import has_sss3_exam_access, exam_student_scope
    derived = has_sss3_exam_access()
    scope = exam_student_scope()

    exams, comparison, arm_counts = [], [], {}
    if session_id:
        exams = scope_query(MockWAECExam.query.filter_by(session_id=session_id),
                            MockWAECExam).order_by(MockWAECExam.exam_number).all()
        if scope is None:
            comparison = MockWAECAnalytics.compare_mock_exams(session_id)
        else:
            for e in exams:
                arm_counts[e.id] = len({r.student_id for r in e.results
                                        if r.student_id in scope})

    return render_template('mock_waec/index.html',
        sessions=sessions, selected_session_id=session_id,
        exams=exams, comparison=comparison,
        derived_exam=derived, arm_counts=arm_counts)


# =============================================================================
# EXAM MANAGEMENT
# =============================================================================

@mock_waec_bp.route('/exam/create', methods=['GET', 'POST'])
@login_required
@csrf_protect
def create_exam():
    sessions = AcademicSession.query.order_by(AcademicSession.name.desc()).all()
    if request.method == 'POST':
        try:
            session_id = request.form.get('session_id', type=int)
            exam_number = request.form.get('exam_number', type=int)
            exam_date = request.form.get('exam_date')
            name = (request.form.get('name') or '').strip()
            description = (request.form.get('description') or '').strip()

            if not session_id or not exam_number or not exam_date:
                flash('Please fill all required fields.', 'error')
                return redirect(url_for('mock_waec.create_exam'))

            new_branch_id = branch_for_new(request.form.get('branch_id', type=int))
            if MockWAECExam.query.filter_by(session_id=session_id, exam_number=exam_number,
                                            branch_id=new_branch_id).first():
                flash(f'Mock WAEC #{exam_number} already exists for this session.', 'error')
                return redirect(url_for('mock_waec.create_exam'))

            try:
                exam_date = datetime.strptime(exam_date, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid date format.', 'error')
                return redirect(url_for('mock_waec.create_exam'))

            session_obj = db.session.get(AcademicSession, session_id)
            if not name:
                ordinals = {1: 'First', 2: 'Second', 3: 'Third', 4: 'Fourth'}
                name = f"{ordinals.get(exam_number, str(exam_number))} Mock WAEC {session_obj.name}"

            exam = MockWAECExam(name=name, exam_number=exam_number, session_id=session_id,
                                exam_date=exam_date, description=description, branch_id=new_branch_id)
            db.session.add(exam)
            db.session.commit()
            flash(f'{exam.display_name} created.', 'success')
            return redirect(url_for('mock_waec.view_exam', exam_id=exam.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating exam: {e}', 'error')

    existing = {str(s.id): [e.exam_number for e in MockWAECExam.query.filter_by(session_id=s.id).all()]
                for s in sessions}
    return render_template('mock_waec/create_exam.html',
        sessions=sessions, existing_exams=existing, exam=None)


@mock_waec_bp.route('/exam/<int:exam_id>/edit', methods=['GET', 'POST'])
@login_required
@csrf_protect
def edit_exam(exam_id):
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    if request.method == 'POST':
        exam.name = (request.form.get('name') or exam.name).strip()
        d = request.form.get('exam_date')
        if d:
            try:
                exam.exam_date = datetime.strptime(d, '%Y-%m-%d').date()
            except ValueError:
                pass
        exam.description = (request.form.get('description') or '').strip()
        exam.is_completed = bool(request.form.get('is_completed'))
        db.session.commit()
        flash('Mock WAEC exam updated.', 'success')
        return redirect(url_for('mock_waec.view_exam', exam_id=exam.id))
    return render_template('mock_waec/create_exam.html', exam=exam,
        sessions=AcademicSession.query.order_by(AcademicSession.name.desc()).all(),
        existing_exams={})


@mock_waec_bp.route('/exam/<int:exam_id>/delete', methods=['POST'])
@admin_required
@csrf_protect
def delete_exam(exam_id):
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    session_id = exam.session_id
    affected = [sid for (sid,) in db.session.query(MockWAECResult.student_id)
                .filter_by(mock_exam_id=exam_id).distinct().all()]
    db.session.delete(exam)
    db.session.commit()
    for sid in affected:
        recompute_student_safe(sid)
    flash('Mock WAEC exam and its results deleted.', 'success')
    return redirect(url_for('mock_waec.index', session_id=session_id))


@mock_waec_bp.route('/exam/<int:exam_id>')
@login_required
def view_exam(exam_id):
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    stats = MockWAECAnalytics.get_exam_statistics(exam_id)

    # Per-student rows (subject grades collapsed) for the results table.
    rows = {}
    for r in MockWAECResult.query.filter_by(mock_exam_id=exam_id).join(Student).all():
        rows.setdefault(r.student_id, {'student': r.student, 'results': []})
        rows[r.student_id]['results'].append(r)
    students = []
    for sid, info in rows.items():
        summary = MockWAECAnalytics._summarise(info['results'])
        students.append({'student': info['student'],
                         'results': sorted(info['results'], key=lambda x: x.subject),
                         **summary})
    students.sort(key=lambda s: (s['credits'], s['average_score'] or 0), reverse=True)
    return render_template('mock_waec/view_exam.html', exam=exam, stats=stats, students=students)


# =============================================================================
# BROADSHEET — the full score+grade matrix, printable, with the summary block
# =============================================================================

@mock_waec_bp.route('/exam/<int:exam_id>/broadsheet')
@login_required
def broadsheet(exam_id):
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    bs = MockWAECAnalytics.get_broadsheet(exam_id)
    return render_template('mock_waec/broadsheet.html', exam=exam, bs=bs,
                           grade_classes=_GRADE_CLASS)


@mock_waec_bp.route('/exam/<int:exam_id>/broadsheet/print')
@login_required
def broadsheet_print(exam_id):
    """A4 print layout of the full broadsheet — bold, full-bleed, nothing hidden.
    With many subjects the columns are split across page-groups (``cols`` per
    group, 0 = all on one wide page) so the text stays large and readable; each
    group repeats the S/N + Name columns and paginates vertically across pages."""
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    return render_template('mock_waec/pdf_preview.html', exam=exam,
        title='Broadsheet (PDF)', show_cols=True, show_orient=True, options=_OPTS_BROADSHEET,
        pdf_url=url_for('mock_waec.broadsheet_pdf_view', exam_id=exam_id),
        back_url=url_for('mock_waec.broadsheet', exam_id=exam_id))


@mock_waec_bp.route('/exam/<int:exam_id>/broadsheet.pdf')
@login_required
@rate_limited('export', max_requests=40, window_minutes=10)
def broadsheet_pdf_view(exam_id):
    """Server-side broadsheet PDF — school header, optional COMPETENCE RESULT
    banner, no admission numbers. Previews inline; ?download=1 to save."""
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    bs = MockWAECAnalytics.get_broadsheet(exam_id)
    if not bs or not bs['rows']:
        flash('No results recorded yet.', 'warning')
        return redirect(url_for('mock_waec.broadsheet', exam_id=exam_id))
    from utils.mock_waec_pdf import broadsheet_pdf
    per = request.args.get('cols', default=8, type=int)
    buf = broadsheet_pdf(bs, exam, _school_profile(),
                         opts=_pdf_opts(), per=(per if per and per > 0 else 0),
                         orient=request.args.get('orient', 'landscape'))
    name = f"broadsheet_{exam.exam_number}_{exam.session.name.replace('/', '-')}.pdf"
    return send_file(buf, mimetype='application/pdf',
                     as_attachment=request.args.get('download') == '1', download_name=name)


@mock_waec_bp.route('/exam/<int:exam_id>/broadsheet/blank')
@login_required
def broadsheet_blank(exam_id):
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    return render_template('mock_waec/pdf_preview.html', exam=exam, show_cols=True,
        show_orient=True, title='Blank recording sheet (PDF)', options=_OPTS_BLANK,
        pdf_url=url_for('mock_waec.broadsheet_blank_pdf', exam_id=exam_id),
        back_url=url_for('mock_waec.view_exam', exam_id=exam_id))


@mock_waec_bp.route('/exam/<int:exam_id>/broadsheet/blank.pdf')
@login_required
@rate_limited('export', max_requests=40, window_minutes=10)
def broadsheet_blank_pdf(exam_id):
    """Empty broadsheet to fill in by hand: every SSS3 student already listed,
    with the subjects they offer as columns (others shaded out)."""
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    students = get_sss3_students()
    smap = student_subject_map(students)
    offered = {s.id: set(smap.get(s.id, {}).get('waec') or []) for s in students}
    union = set().union(*offered.values()) if offered else set()
    subjects = MockWAECAnalytics._ordered_subjects(union or set(WAEC_DEFAULT_SUBJECTS))
    from utils.mock_waec_pdf import blank_broadsheet_pdf
    per = request.args.get('cols', default=0, type=int)
    buf = blank_broadsheet_pdf(students, offered, subjects, exam, _school_profile(),
                               opts=_pdf_opts(), per=(per if per and per > 0 else 0),
                               orient=request.args.get('orient', 'landscape'))
    name = f"recording_sheet_{exam.exam_number}_{exam.session.name.replace('/', '-')}.pdf"
    return send_file(buf, mimetype='application/pdf',
                     as_attachment=request.args.get('download') == '1', download_name=name)


@mock_waec_bp.route('/exam/<int:exam_id>/broadsheet/export')
@login_required
@rate_limited('export', max_requests=40, window_minutes=10)
def broadsheet_export(exam_id):
    """Wide broadsheet workbook: a column per subject (score + grade), with the
    per-subject offered/passed/failed/average rows beneath, just like the sheet."""
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    bs = MockWAECAnalytics.get_broadsheet(exam_id)
    subjects = bs['subjects']

    wb = Workbook()
    ws = wb.active
    ws.title = 'Broadsheet'
    ws.append(['S/N', 'Student'] + subjects + ['Credits', 'Avg %'])
    for i, row in enumerate(bs['rows'], 1):
        line = [i, row['student'].full_name]
        for subj in subjects:
            r = row['cells'].get(subj)
            line.append(f'{r.score} {r.grade}' if r and r.score is not None else '')
        line += [row['credits'], row['average_score'] if row['average_score'] is not None else '']
        ws.append(line)

    ws.append([])
    ss = bs['subject_summary']
    def _summary_row(label, fn):
        ws.append(['', label] + [fn(ss[s]) for s in subjects] + ['', ''])
    _summary_row('No. offered', lambda d: d['offered'])
    _summary_row('No. passed', lambda d: d['passed'])
    _summary_row('No. failed', lambda d: d['failed'])
    _summary_row('Average score %', lambda d: d['avg_score'] if d['avg_score'] is not None else '')
    _summary_row('Average grade', lambda d: d['avg_grade'])

    return xlsx_response(wb, f'mock_waec_broadsheet_{exam.exam_number}_'
                             f'{exam.session.name.replace("/", "-")}.xlsx')


# Grade -> CSS badge tone, shared by the broadsheet and grid templates.
_GRADE_CLASS = {
    'A1': 'a1', 'B2': 'b', 'B3': 'b', 'C4': 'c', 'C5': 'c', 'C6': 'c',
    'D7': 'd', 'E8': 'e', 'F9': 'f',
}


@mock_waec_bp.route('/exam/<int:exam_id>/analytics')
@login_required
def analytics(exam_id):
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    data = MockWAECAnalytics.get_analytics(exam_id)
    return render_template('mock_waec/analytics.html', exam=exam, a=data,
                           grade_classes=_GRADE_CLASS)


@mock_waec_bp.route('/exam/<int:exam_id>/subject/<subject>')
@login_required
def subject_analysis(exam_id, subject):
    """Full analysis of one subject within a Mock WAEC exam: grade distribution
    (A1…F9 counts + %), score stats, credit/distinction/pass/fail and the
    candidate list (with score) grouped by grade."""
    from utils.analytics_service import AcademicAnalytics
    from models.mock_waec import DISTINCTION_GRADES
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    results = MockWAECResult.query.filter_by(mock_exam_id=exam_id, subject=subject).all()
    data = None
    if results:
        counts = {g: 0 for g in WAEC_GRADES}
        scores, by_grade = [], {g: [] for g in WAEC_GRADES}
        sids = list({r.student_id for r in results})
        studs = {s.id: s for s in Student.query.filter(Student.id.in_(sids or [-1])).all()}
        for r in results:
            g = r.grade if r.grade in counts else 'F9'
            counts[g] += 1
            if r.score is not None:
                scores.append(r.score)
            st = studs.get(r.student_id)
            by_grade[g].append({'name': f'{st.surname} {st.first_name}' if st else '—',
                                'admission_no': st.student_id if st else '',
                                'student_id': r.student_id, 'score': r.score})
        for g in by_grade:
            by_grade[g].sort(key=lambda x: (x['score'] is None, -(x['score'] or 0)))
        total = len(results)
        credit = sum(counts[g] for g in PASS_GRADES)
        distinction = sum(counts[g] for g in DISTINCTION_GRADES)
        fail = counts['E8'] + counts['F9']
        avg_pts = round(sum(AcademicAnalytics.GRADE_AVERAGE_POINTS.get(r.grade, 0)
                            for r in results) / total, 2)
        data = {
            'subject': subject, 'total': total, 'counts': counts,
            'distribution': [{'grade': g, 'count': counts[g],
                              'pct': round(counts[g] / total * 100, 1)} for g in WAEC_GRADES],
            'a1_count': counts['A1'],
            'credit_count': credit, 'credit_rate': round(credit / total * 100, 1),
            'distinction_count': distinction, 'distinction_rate': round(distinction / total * 100, 1),
            'pass_rate': round(credit / total * 100, 1),
            'fail_count': fail, 'fail_rate': round(fail / total * 100, 1),
            'average_points': avg_pts, 'max_points': 9,
            'avg_score': round(sum(scores) / len(scores), 1) if scores else None,
            'max_score': max(scores) if scores else None,
            'min_score': min(scores) if scores else None,
            'by_grade': by_grade,
        }
    return render_template('mock_waec/subject_analysis.html', exam=exam, subject=subject,
                           data=data, grades=WAEC_GRADES, grade_classes=_GRADE_CLASS)


@mock_waec_bp.route('/exam/<int:exam_id>/deep')
@login_required
def deep(exam_id):
    """Decision-grade deep analytics for one Mock WAEC exam — per subject, per
    teacher, per class arm, with evidence-based recommendations."""
    from utils.mock_deep_analytics import deep_analytics
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    data = deep_analytics('waec', exam_id)
    return render_template('mock_waec/deep_analytics.html', exam=exam, d=data,
                           grade_classes=_GRADE_CLASS,
                           compose_base=url_for('comms.compose'))


@mock_waec_bp.route('/trends')
@login_required
def trends():
    """Longitudinal deep analytics across many Mock WAEC exams — one session, or
    all sessions (year-over-year progress)."""
    from utils.mock_deep_analytics import deep_trends
    scope = request.args.get('scope')
    session_id = request.args.get('session_id', type=int)
    active = get_active_session()
    if scope != 'all' and not session_id and active:
        session_id = active.id
    if scope == 'all':
        session_id = None
    data = deep_trends('waec', session_id=session_id)
    for p in data.get('periods', []):
        p['deep_url'] = url_for('mock_waec.deep', exam_id=p['exam_id'])
    sessions = AcademicSession.query.order_by(AcademicSession.name.desc()).all()
    return render_template('mock_waec/deep_trends.html', d=data,
                           scope='all' if session_id is None else 'session',
                           selected_session_id=session_id or '',
                           sessions=sessions,
                           compose_base=url_for('comms.compose'))


@mock_waec_bp.route('/trends/export')
@login_required
def trends_export():
    """Export the Mock WAEC progress trends. ``format`` = pdf | excel | image."""
    from utils.mock_deep_analytics import deep_trends
    from utils.mock_deep_report import trends_pdf, trends_xlsx, trends_png, trends_filename
    from utils.web_exports import pdf_response, xlsx_response, png_response
    scope = request.args.get('scope')
    session_id = request.args.get('session_id', type=int)
    if scope != 'all' and not session_id:
        active = get_active_session()
        session_id = active.id if active else None
    if scope == 'all':
        session_id = None
    data = deep_trends('waec', session_id=session_id)
    if not data or data['meta'].get('insufficient'):
        flash('Need at least two mocks with results to chart progress.', 'warning')
        return redirect(url_for('mock_waec.trends', scope=scope or '', session_id=session_id or ''))
    fmt = (request.args.get('format') or 'pdf').lower()
    meta = data['meta']
    if fmt in ('excel', 'xlsx'):
        return xlsx_response(trends_xlsx(data), trends_filename(meta, 'xlsx'))
    if fmt in ('image', 'png'):
        return png_response(trends_png(data), trends_filename(meta, 'png'), inline=False)
    return pdf_response(trends_pdf(data), trends_filename(meta, 'pdf'), inline=False)


@mock_waec_bp.route('/exam/<int:exam_id>/deep/export')
@login_required
def deep_export(exam_id):
    """Export the Mock WAEC deep analytics. ``format`` = pdf | excel | image."""
    from utils.mock_deep_analytics import deep_analytics
    from utils.mock_deep_report import deep_pdf, deep_xlsx, deep_png, deep_filename
    from utils.web_exports import pdf_response, xlsx_response, png_response
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    data = deep_analytics('waec', exam_id)
    if not data or data['meta'].get('empty'):
        flash('No results yet — enter scores to unlock deep analytics.', 'warning')
        return redirect(url_for('mock_waec.deep', exam_id=exam_id))
    fmt = (request.args.get('format') or 'pdf').lower()
    meta = data['meta']
    if fmt in ('excel', 'xlsx'):
        return xlsx_response(deep_xlsx(data), deep_filename(meta, 'xlsx'))
    if fmt in ('image', 'png'):
        return png_response(deep_png(data), deep_filename(meta, 'png'), inline=False)
    return pdf_response(deep_pdf(data), deep_filename(meta, 'pdf'), inline=False)


@mock_waec_bp.route('/exam/<int:exam_id>/validation')
@login_required
def validation(exam_id):
    """How well this Mock WAEC predicted actual WAEC grades (per subject)."""
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    from utils.mock_validation import waec_validation
    from models import WAECResult
    year = request.args.get('year', type=int)
    data = waec_validation(mock_exam_id=exam.id, year=year)
    years = sorted({y for (y,) in db.session.query(WAECResult.exam_year).distinct().all()}, reverse=True)
    return render_template('mock_waec/validation.html', exam=exam, v=data,
                           years=years, selected_year=year or '')


@mock_waec_bp.route('/exam/<int:exam_id>/validation/export')
@login_required
def validation_export(exam_id):
    """Export the Mock→actual WAEC validation. ``format`` = pdf | excel."""
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    from utils.mock_validation import waec_validation
    from utils.mock_validation_report import validation_pdf, validation_xlsx
    from utils.web_exports import pdf_response, xlsx_response
    year = request.args.get('year', type=int)
    data = waec_validation(mock_exam_id=exam.id, year=year)
    if not data or data['meta'].get('insufficient'):
        flash('Not enough matched subject grades to validate this mock yet.', 'warning')
        return redirect(url_for('mock_waec.validation', exam_id=exam.id))
    stem = 'waec_mock_validation'
    if (request.args.get('format') or 'pdf').lower() in ('excel', 'xlsx'):
        return xlsx_response(validation_xlsx(data), f'{stem}.xlsx')
    return pdf_response(validation_pdf(data), f'{stem}.pdf', inline=False)


# =============================================================================
# GRID ENTRY — fast spreadsheet-style entry across the whole cohort
# =============================================================================

@mock_waec_bp.route('/exam/<int:exam_id>/grid', methods=['GET', 'POST'])
@login_required
@csrf_protect
def grid_entry(exam_id):
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    students = get_sss3_students()

    # Column subjects: the ones chosen (checkbox form), else the exam's existing
    # subjects merged with the sensible defaults.
    existing = [s for (s,) in db.session.query(MockWAECResult.subject)
                .filter_by(mock_exam_id=exam_id).distinct().all()]
    chosen = [c for c in request.values.getlist('col') if c in WAEC_SUBJECTS]
    if chosen:
        subjects = MockWAECAnalytics._ordered_subjects(set(chosen))
    else:
        subjects = MockWAECAnalytics._ordered_subjects(set(existing) | set(WAEC_DEFAULT_SUBJECTS))

    if request.method == 'POST' and request.form.get('action') == 'save':
        cols = [c for c in request.form.getlist('col') if c in WAEC_SUBJECTS] or subjects
        touched, saved = set(), 0
        for s in students:
            for subj in cols:
                raw = (request.form.get(f'score_{s.id}_{_slug(subj)}') or '').strip()
                if raw == '':
                    continue                       # blank = leave untouched
                try:
                    score = max(0, min(100, int(round(float(raw)))))
                except (TypeError, ValueError):
                    continue
                _upsert_result(s.id, exam_id, subj, score, None)
                touched.add(s.id)
                saved += 1
        db.session.commit()
        for sid in touched:
            recompute_student_safe(sid)
        flash(f'Saved {saved} score(s) for {len(touched)} student(s).', 'success')
        return redirect(url_for('mock_waec.grid_entry', exam_id=exam_id, col=cols))

    # Prefill from existing results.
    score_map = {(r.student_id, r.subject): r.score
                 for r in MockWAECResult.query.filter_by(mock_exam_id=exam_id).all()}
    return render_template('mock_waec/grid_entry.html',
        exam=exam, students=students, subjects=subjects, all_subjects=WAEC_SUBJECTS,
        score_map=score_map, slug=_slug)


def _slug(subject):
    """Form-field-safe key for a subject name."""
    return re.sub(r'[^a-z0-9]+', '-', (subject or '').lower()).strip('-')


# =============================================================================
# RESULT ENTRY — single student
# =============================================================================

@mock_waec_bp.route('/exam/<int:exam_id>/results/add', methods=['GET', 'POST'])
@login_required
@csrf_protect
def add_result(exam_id):
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    # Don't offer students who already have a result entered for this mock.
    entered = {sid for (sid,) in db.session.query(MockWAECResult.student_id)
               .filter_by(mock_exam_id=exam_id).distinct()}
    students = [s for s in get_sss3_students() if s.id not in entered]

    if request.method == 'POST':
        student_id = request.form.get('student_id', type=int)
        if not student_id:
            flash('Please select a student.', 'error')
            return redirect(url_for('mock_waec.add_result', exam_id=exam_id))
        from utils.access_control import assert_exam_student
        assert_exam_student(student_id)          # own-arm only for SSS3 teachers
        subjects = request.form.getlist('subject[]')
        scores = request.form.getlist('score[]')
        grades = request.form.getlist('grade[]')
        saved = 0
        for i, subject in enumerate(subjects):
            subject = (subject or '').strip()
            raw = scores[i] if i < len(scores) else ''
            if not subject or raw in (None, ''):
                continue
            try:
                score = max(0, min(100, int(raw)))
            except (TypeError, ValueError):
                continue
            # Honour an edited grade only if it's a valid WAEC grade; else derive.
            supplied = (grades[i].strip().upper() if i < len(grades) else '')
            grade = supplied if supplied in WAEC_GRADES else None
            _upsert_result(student_id, exam_id, subject, score, grade)
            saved += 1
        db.session.commit()
        recompute_student_safe(student_id)
        flash(f'{saved} subject result(s) saved.', 'success')
        # SSS3 arm teachers can't open the cohort exam view — send them to the
        # student's own progress page instead.
        from utils.access_control import has_sss3_exam_access
        if has_sss3_exam_access():
            return redirect(url_for('mock_waec.student_progress', student_id=student_id))
        return redirect(url_for('mock_waec.view_exam', exam_id=exam_id))

    return render_template('mock_waec/add_result.html',
        exam=exam, students=students, subjects=WAEC_SUBJECTS, grades=WAEC_GRADES,
        default_subjects=WAEC_DEFAULT_SUBJECTS, stream_defaults=STREAM_WAEC_SUBJECTS,
        subject_map=student_subject_map(students))


# =============================================================================
# RESULT ENTRY — paste & preview bulk importer
# =============================================================================

def _name_tokens(text):
    """Normalised alphabetic tokens of a name (uppercase, punctuation dropped)."""
    return [t for t in re.sub(r'[^A-Za-z ]+', ' ', (text or '').upper()).split() if t]


def _build_student_index():
    """Index the SSS3 cohort for flexible matching: by admission number, by exact
    normalised full name, and by (surname, first-name) token sets so a pasted name
    can match even when middle names are missing, shortened, or reordered."""
    by_admission, by_fullname, token_rows = {}, {}, []
    for s in get_sss3_students():
        if s.student_id:
            by_admission[s.student_id.strip().upper()] = s
        full = _name_tokens(s.full_name)
        by_fullname.setdefault(' '.join(full), s)
        # Required anchors: surname + first name (middle names are optional).
        anchors = set(_name_tokens(s.surname)) | set(_name_tokens(s.first_name))
        token_rows.append((s, anchors, set(full)))
    return by_admission, by_fullname, token_rows


def _token_covered(needle, haystack):
    """True if *needle* matches any token in *haystack* exactly or as a >=3-char
    prefix (so 'Tobi' matches 'Tobiloba' and vice-versa)."""
    for tok in haystack:
        if tok == needle or (len(needle) >= 3 and len(tok) >= 3
                             and (tok.startswith(needle) or needle.startswith(tok))):
            return True
    return False


def _resolve_student(index, ident):
    """Resolve a pasted identifier to a student. Returns ``(student, message)``;
    *student* is ``None`` when there is no confident single match."""
    by_admission, by_fullname, token_rows = index
    key = ident.strip().upper()
    if key in by_admission:                       # admission number is exact & unambiguous
        return by_admission[key], ''

    toks = _name_tokens(ident)
    norm = ' '.join(toks)
    if norm in by_fullname:
        return by_fullname[norm], ''
    if not toks:
        return None, f'No SSS3 student matches "{ident}"'

    # Anchor match: every required (surname + first name) token of a candidate is
    # present in the pasted name; pasted middle names are ignored.
    in_set = set(toks)
    candidates = [s for s, anchors, _full in token_rows
                  if anchors and all(_token_covered(a, in_set) for a in anchors)]
    if len(candidates) == 1:
        return candidates[0], 'Matched by name (middle name ignored)' if norm != ' '.join(
            _name_tokens(candidates[0].full_name)) else ''
    if len(candidates) > 1:
        names = ', '.join(c.full_name for c in candidates[:3])
        return None, f'"{ident}" matches {len(candidates)} students ({names}…) — use admission no'
    return None, f'No SSS3 student matches "{ident}"'


def _parse_paste(text):
    """Parse pasted CSV lines into preview rows.

    Each line: ``student, subject, score[, grade]`` where *student* is an
    admission number or name (middle names optional), and *subject* may be an
    abbreviation (Eng, Maths, CRS…). Grade is optional (auto-derived from score).
    Returns ``(rows, ok_count)`` — every row carries a status so the preview can
    show exactly what will (and won't) be imported.
    """
    index = _build_student_index()
    rows, ok = [], 0
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(',')]
        row = {'lineno': lineno, 'raw': line, 'status': 'error', 'message': '',
               'student': None, 'student_id': None, 'student_name': parts[0] if parts else '',
               'subject': '', 'score': None, 'grade': None}
        if len(parts) < 3:
            row['message'] = 'Need at least: student, subject, score'
            rows.append(row)
            continue

        ident, subject_raw, score_raw = parts[0], parts[1], parts[2]
        grade_raw = parts[3] if len(parts) >= 4 else ''

        # Resolve student (admission no, exact name, or anchor/middle-name match).
        student, msg = _resolve_student(index, ident)
        if not student:
            row['message'] = msg
            rows.append(row)
            continue
        row['student'] = student
        row['student_id'] = student.id
        row['student_name'] = student.full_name
        if msg:
            row['message'] = msg

        # Canonicalise subject (handles abbreviations); keep raw if unrecognised.
        canon = canonical_subject(subject_raw)
        row['subject'] = canon or subject_raw.strip().title()
        if not canon:
            row['message'] = f'Unrecognised subject "{subject_raw}" (will still be saved)'

        # Score.
        try:
            score = int(round(float(score_raw)))
        except (TypeError, ValueError):
            row['message'] = f'Invalid score "{score_raw}"'
            rows.append(row)
            continue
        if not 0 <= score <= 100:
            row['message'] = f'Score {score} out of range (0-100)'
            rows.append(row)
            continue
        row['score'] = score

        # Grade: honour a valid supplied grade, else derive.
        grade = grade_raw.upper() if grade_raw else ''
        row['grade'] = grade if grade in WAEC_GRADES else waec_grade_from_score(score)

        row['status'] = 'warning' if row['message'] else 'ok'
        ok += 1
        rows.append(row)
    return rows, ok


@mock_waec_bp.route('/exam/<int:exam_id>/results/paste', methods=['GET', 'POST'])
@login_required
@csrf_protect
def paste_entry(exam_id):
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    text = request.form.get('data', '')
    action = request.form.get('action')

    if request.method == 'POST' and action == 'confirm':
        rows, _ = _parse_paste(text)          # re-parse: never trust a serialized blob
        touched, saved = set(), 0
        for row in rows:
            if row['status'] in ('ok', 'warning') and row['student_id']:
                _upsert_result(row['student_id'], exam_id, row['subject'],
                               row['score'], row['grade'])
                touched.add(row['student_id'])
                saved += 1
        db.session.commit()
        for sid in touched:
            recompute_student_safe(sid)
        flash(f'Imported {saved} result(s) for {len(touched)} student(s).', 'success')
        return redirect(url_for('mock_waec.view_exam', exam_id=exam_id))

    preview = None
    if request.method == 'POST' and action == 'preview':
        rows, ok = _parse_paste(text)
        preview = {'rows': rows, 'ok': ok, 'errors': sum(1 for r in rows if r['status'] == 'error')}

    return render_template('mock_waec/paste_entry.html', exam=exam, text=text, preview=preview)


def _upsert_result(student_id, exam_id, subject, score, grade=None):
    """Insert or update one subject result (no commit)."""
    row = MockWAECResult.query.filter_by(
        student_id=student_id, mock_exam_id=exam_id, subject=subject).first()
    if row is None:
        row = MockWAECResult(student_id=student_id, mock_exam_id=exam_id, subject=subject)
        db.session.add(row)
    row.apply_score(score, grade)
    return row


@mock_waec_bp.route('/result/<int:result_id>/delete', methods=['POST'])
@login_required
@csrf_protect
def delete_result(result_id):
    result = db.get_or_404(MockWAECResult, result_id)
    exam = db.session.get(MockWAECExam, result.mock_exam_id)
    require_branch_access(exam.branch_id)
    exam_id, student_id = result.mock_exam_id, result.student_id
    db.session.delete(result)
    db.session.commit()
    recompute_student_safe(student_id)
    flash('Result deleted.', 'success')
    return redirect(url_for('mock_waec.view_exam', exam_id=exam_id))


# =============================================================================
# PER-STUDENT CRUD — edit / add / delete a single student's subject results
# =============================================================================

@mock_waec_bp.route('/exam/<int:exam_id>/student/<int:student_id>/edit',
                    methods=['GET', 'POST'])
@login_required
@csrf_protect
def edit_student_results(exam_id, student_id):
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    student = db.get_or_404(Student, student_id)
    from utils.access_control import assert_exam_student
    assert_exam_student(student_id)          # own-arm only for SSS3 teachers

    def _clean_score(raw):
        return max(0, min(100, int(round(float(raw)))))

    if request.method == 'POST':
        if request.form.get('delete_id'):                       # delete one subject
            rid = request.form.get('delete_id', type=int)
            row = MockWAECResult.query.filter_by(
                id=rid, mock_exam_id=exam_id, student_id=student_id).first()
            if row:
                subj = row.subject
                db.session.delete(row)
                db.session.commit()
                recompute_student_safe(student_id)
                flash(f'{subj} removed.', 'success')
        elif request.form.get('add'):                           # add a subject
            subject = (request.form.get('subject') or '').strip()
            raw = (request.form.get('score') or '').strip()
            grade_in = (request.form.get('grade') or '').strip().upper()
            if not subject or raw == '':
                flash('Pick a subject and enter a score.', 'error')
            else:
                try:
                    grade = grade_in if grade_in in WAEC_GRADES else None
                    _upsert_result(student_id, exam_id, subject, _clean_score(raw), grade)
                    db.session.commit()
                    recompute_student_safe(student_id)
                    flash(f'{subject} saved.', 'success')
                except (TypeError, ValueError):
                    flash('Invalid score — use a number 0–100.', 'error')
        else:                                                    # save all edits
            changed = 0
            for row in MockWAECResult.query.filter_by(
                    mock_exam_id=exam_id, student_id=student_id).all():
                raw = (request.form.get(f'score_{row.id}') or '').strip()
                if raw == '':
                    continue
                try:
                    score = _clean_score(raw)
                except (TypeError, ValueError):
                    continue
                grade_in = (request.form.get(f'grade_{row.id}') or '').strip().upper()
                row.apply_score(score, grade_in if grade_in in WAEC_GRADES else None)
                changed += 1
            db.session.commit()
            recompute_student_safe(student_id)
            flash(f'Updated {changed} subject(s).', 'success')
        return redirect(url_for('mock_waec.edit_student_results',
                                exam_id=exam_id, student_id=student_id))

    results = (MockWAECResult.query
               .filter_by(mock_exam_id=exam_id, student_id=student_id)
               .order_by(MockWAECResult.subject).all())
    have = {r.subject for r in results}
    available = [s for s in WAEC_SUBJECTS if s not in have]
    summary = MockWAECAnalytics._summarise(results) if results else None
    return render_template('mock_waec/edit_student.html', exam=exam, student=student,
        results=results, available=available, grades=WAEC_GRADES, summary=summary)


# =============================================================================
# PRINTABLE RESULT SLIPS — one student, or every student
# =============================================================================

def _school_profile():
    """School identity for printed results (incl. logo), from Settings → School."""
    from utils.school import school_profile
    return school_profile()


def _slips_for(exam_id, student_id=None):
    """List of {student, summary} slips — one student or the whole exam (A–Z)."""
    if student_id is not None:
        student = db.get_or_404(Student, student_id)
        return [{'student': student,
                 'summary': MockWAECAnalytics.get_student_exam_summary(student_id, exam_id)}]
    by_student = {}
    for r in MockWAECResult.query.filter_by(mock_exam_id=exam_id).join(Student).all():
        by_student.setdefault(r.student_id, {'student': r.student, 'results': []})
        by_student[r.student_id]['results'].append(r)
    slips = []
    for info in by_student.values():
        summary = MockWAECAnalytics._summarise(info['results'])
        summary['results'] = sorted(info['results'], key=lambda x: x.subject)
        slips.append({'student': info['student'], 'summary': summary})
    slips.sort(key=lambda s: (s['student'].surname or '', s['student'].first_name or ''))
    return slips


# Optional blocks for the printed PDFs — each included unless ?<flag>=0.
_PDF_FLAGS = ('title', 'address', 'contact', 'motto', 'summary', 'signatures', 'grades')


def _pdf_opts():
    return {f: request.args.get(f, '1') != '0' for f in _PDF_FLAGS}


def _signers():
    """Which signature line(s) the result slip should carry."""
    v = request.args.get('signers', 'both')
    return v if v in ('both', 'principal', 'teacher', 'none') else 'both'


# Detail checkboxes shown on each preview page (param, label) — all on by default.
_OPTS_BROADSHEET = [('title', '“COMPETENCE RESULT” heading'), ('address', 'School address'),
                    ('contact', 'Phone / email'), ('motto', 'School motto'),
                    ('summary', 'Subject summary rows'), ('grades', 'Grade key')]
_OPTS_BLANK = [('title', '“COMPETENCE RESULT” heading'), ('address', 'School address'),
               ('contact', 'Phone / email'), ('motto', 'School motto'),
               ('summary', 'Blank summary rows'), ('grades', 'Grade key')]
_OPTS_SLIP = [('title', '“COMPETENCE RESULT” heading'), ('address', 'School address'),
              ('contact', 'Phone / email'), ('motto', 'School motto'),
              ('summary', 'Summary box')]


@mock_waec_bp.route('/exam/<int:exam_id>/student/<int:student_id>/slip')
@login_required
def result_slip(exam_id, student_id):
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    from utils.access_control import assert_exam_student
    assert_exam_student(student_id)          # own-arm only for SSS3 teachers
    student = db.get_or_404(Student, student_id)
    return render_template('mock_waec/pdf_preview.html', exam=exam, show_cols=False,
        show_signers=True, title=f'Result — {student.full_name}', options=_OPTS_SLIP,
        pdf_url=url_for('mock_waec.result_slip_pdf', exam_id=exam_id, student_id=student_id),
        back_url=url_for('mock_waec.view_exam', exam_id=exam_id))


@mock_waec_bp.route('/exam/<int:exam_id>/slips')
@login_required
def result_slips_all(exam_id):
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    return render_template('mock_waec/pdf_preview.html', exam=exam, show_cols=False,
        show_signers=True, title='Results (PDF)', options=_OPTS_SLIP,
        pdf_url=url_for('mock_waec.result_slips_pdf_view', exam_id=exam_id),
        back_url=url_for('mock_waec.view_exam', exam_id=exam_id))


@mock_waec_bp.route('/exam/<int:exam_id>/student/<int:student_id>/slip.pdf')
@login_required
@rate_limited('export', max_requests=40, window_minutes=10)
def result_slip_pdf(exam_id, student_id):
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    from utils.access_control import assert_exam_student
    assert_exam_student(student_id)          # own-arm only for SSS3 teachers
    from utils.mock_waec_pdf import result_slips_pdf
    buf = result_slips_pdf(_slips_for(exam_id, student_id), exam,
                           _school_profile(), opts=_pdf_opts(), signers=_signers())
    student = db.session.get(Student, student_id)
    name = f"result_{(student.full_name if student else student_id)}.pdf".replace(' ', '_')
    return send_file(buf, mimetype='application/pdf',
                     as_attachment=request.args.get('download') == '1', download_name=name)


@mock_waec_bp.route('/exam/<int:exam_id>/slips.pdf')
@login_required
@rate_limited('export', max_requests=40, window_minutes=10)
def result_slips_pdf_view(exam_id):
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    from utils.mock_waec_pdf import result_slips_pdf
    buf = result_slips_pdf(_slips_for(exam_id), exam, _school_profile(),
                           opts=_pdf_opts(), signers=_signers())
    name = f"results_{exam.exam_number}_{exam.session.name.replace('/', '-')}.pdf"
    return send_file(buf, mimetype='application/pdf',
                     as_attachment=request.args.get('download') == '1', download_name=name)


# =============================================================================
# STUDENT PROGRESSION
# =============================================================================

@mock_waec_bp.route('/student/<int:student_id>')
@login_required
def student_progress(student_id):
    student = db.get_or_404(Student, student_id)
    require_branch_access(student.branch_id)
    from utils.access_control import assert_exam_student
    assert_exam_student(student_id)          # own-arm only for SSS3 teachers
    progress = MockWAECAnalytics.get_student_progress(student_id)
    prediction = MockWAECAnalytics.predict_waec(student_id)
    return render_template('mock_waec/student_progress.html',
        student=student, progress=progress, prediction=prediction)


# =============================================================================
# EXPORT
# =============================================================================

@mock_waec_bp.route('/exam/<int:exam_id>/export')
@login_required
def export_results(exam_id):
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Mock WAEC'
    ws.append(['Student', 'Subject', 'Score', 'Grade'])
    results = (MockWAECResult.query.filter_by(mock_exam_id=exam_id)
               .join(Student).order_by(Student.surname, MockWAECResult.subject).all())
    for r in results:
        ws.append([r.student.full_name, r.subject, r.score, r.grade])
    return xlsx_response(wb, f'mock_waec_{exam.exam_number}_{exam.session.name.replace("/", "-")}.xlsx')
