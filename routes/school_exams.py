"""JSS3 (BECE) and Basic 6 (Common Entrance) external exams — state + federal.

Two **separate, self-contained** blueprints built from one factory, mirroring
how the timetable generator keeps JSS and SSS apart:

* ``jss3_exams``   → ``/jss3-exams/…``   (State BECE  + NECO BECE)
* ``basic6_exams`` → ``/basic6-exams/…`` (State Common Entrance + NCEE)

Each has its own dashboard, result entry (single / grid / CSV paste), student
record, subject drill-down, full analytics, state-vs-federal comparison,
Excel export and settings. A third tiny blueprint, ``exam_levels``, is the
level selector (SSS3 / JSS3 / Basic 6), like ``/generator/``.

All three map to the ``external_exams`` permission module; each level is also
its own sub-section ('jss3' / 'basic6') so access can be granted per level.
"""
from datetime import date as _date

from flask import (Blueprint, render_template, request, redirect, url_for, flash, abort)

from models import db, Student
from models.models_school_exams import (
    LEVEL_META, BODIES, KINDS, SchoolExamResult, SchoolExamCandidate, get_scheme,
)
from utils.access_control import login_required
from utils.branch_scope import require_branch_access
from utils.audit import log_action
from utils import school_exams as svc


def _default_year(years):
    from utils.helpers import resolve_exam_year
    return resolve_exam_year(request.args.get('year', type=int), years) or _date.today().year


def _body_or_404(body):
    if body not in BODIES:
        abort(404)
    return body


def _ctx(level, bp_name, body=None, **extra):
    L = LEVEL_META[level]
    ctx = {'L': L, 'level': level, 'bp': bp_name, 'bodies': BODIES, 'kinds': KINDS,
           'ch': svc.charts}
    ctx['body_links'] = _body_links()
    if body:
        ctx['body'] = body
        ctx['body_meta'] = L['bodies'][body]
        ctx['scheme'] = get_scheme(level, body)
    ctx.update(extra)
    return ctx


def _body_links():
    """{body: url} — the current page re-pointed at each exam body, keeping the
    year / subject / student so the State ↔ Federal toggle stays in context."""
    out = {}
    ep = request.endpoint
    if not ep or request.method != 'GET':
        return out
    for b in BODIES:
        va = dict(request.view_args or {})
        args = {k: v for k, v in request.args.items() if k not in ('q', 'body', 'col')}
        if 'body' in va:
            va['body'] = b
        else:
            args['body'] = b
        try:
            out[b] = url_for(ep, **va, **args)
        except Exception:
            pass
    return out


def _student_or_404(level, student_id):
    st = db.get_or_404(Student, student_id)
    require_branch_access(st.branch_id)
    return st


def make_blueprint(level):
    bp_name = f'{level}_exams'
    bp = Blueprint(bp_name, __name__, url_prefix=f'/{level}-exams')
    L = LEVEL_META[level]

    @bp.before_request
    def _heal():
        svc.ensure_school_exam_schema()

    # ------------------------------------------------------------------ #
    # Dashboard
    # ------------------------------------------------------------------ #
    @bp.route('/')
    @login_required
    def dashboard():
        body = _body_or_404(request.args.get('body', 'state'))
        years = svc.years_for(level, body)
        year = _default_year(years)
        stats = svc.year_stats(level, body, year)
        search = (request.args.get('q') or '').strip().lower()
        cands = stats['candidates']
        if search:
            cands = [c for c in cands if search in c['name'].lower()
                     or search in (c['student_code'] or '').lower()
                     or search in (c['exam_number'] or '').lower()]
        cands, sort = svc.sort_candidates(cands, request.args.get('sort', 'position'))
        other = 'federal' if body == 'state' else 'state'
        return render_template('school_exams/dashboard.html', **_ctx(
            level, bp_name, body, years=years, year=year, stats=stats,
            candidates=cands, search=search, other=other, sort=sort,
            sorts=[(k, v[0]) for k, v in svc.CANDIDATE_SORTS.items()],
            other_years=svc.years_for(level, other),
            trend=svc.trend(level, body)))

    # ------------------------------------------------------------------ #
    # Analytics
    # ------------------------------------------------------------------ #
    @bp.route('/analytics')
    @login_required
    def analytics():
        body = _body_or_404(request.args.get('body', 'state'))
        years = svc.years_for(level, body)
        year = _default_year(years)
        stats = svc.year_stats(level, body, year)
        return render_template('school_exams/analytics.html', **_ctx(
            level, bp_name, body, years=years, year=year, stats=stats,
            trend=svc.trend(level, body),
            ive=svc.internal_vs_external(level, stats['candidates'])))

    @bp.route('/compare')
    @login_required
    def compare():
        years = sorted(set(svc.years_for(level, 'state')) | set(svc.years_for(level, 'federal')),
                       reverse=True)
        year = _default_year(years)
        return render_template('school_exams/compare.html', **_ctx(
            level, bp_name, None, years=years, year=year,
            cmp=svc.compare_bodies(level, year),
            trend_state=svc.trend(level, 'state'),
            trend_federal=svc.trend(level, 'federal')))

    @bp.route('/subject/<body>/<path:subject>')
    @login_required
    def subject(body, subject):
        _body_or_404(body)
        years = svc.years_for(level, body)
        year = _default_year(years)
        return render_template('school_exams/subject.html', **_ctx(
            level, bp_name, body, years=years, year=year, subject=subject,
            d=svc.subject_detail(level, body, year, subject)))

    # ------------------------------------------------------------------ #
    # Single-student entry
    # ------------------------------------------------------------------ #
    @bp.route('/<body>/add', methods=['GET', 'POST'])
    @login_required
    def add_result(body):
        _body_or_404(body)
        scheme = get_scheme(level, body)
        students = svc.level_students(level)
        allowed = {s.id for s in students}
        if request.method == 'POST':
            sid = request.form.get('student_id', type=int)
            year = request.form.get('exam_year', type=int)
            if not sid or not year:
                flash('Choose a student and the exam year.', 'error')
                return redirect(url_for(f'{bp_name}.add_result', body=body))
            if sid not in allowed:
                flash(f'That student is not a {L["class_label"]} candidate in your branch.', 'error')
                return redirect(url_for(f'{bp_name}.add_result', body=body))
            rows = list(zip(request.form.getlist('subject[]'), request.form.getlist('score[]'),
                            request.form.getlist('grade[]')))
            cand = {k: request.form.get(k) for k in
                    ('exam_number', 'centre', 'total_score', 'placement', 'admitted', 'remarks')}
            try:
                n = svc.save_student_results(scheme, sid, year, rows, candidate=cand, replace=True)
                db.session.commit()
            except Exception as e:  # pragma: no cover — surfaced to the user
                db.session.rollback()
                flash(f'Could not save: {e}', 'error')
                return redirect(url_for(f'{bp_name}.add_result', body=body, student_id=sid))
            st = db.session.get(Student, sid)
            log_action(f'{bp_name}.save', detail=f'{scheme.exam_name} {year}: {n} subject(s)', target=st)
            flash(f'Saved {n} {scheme.exam_name} result(s) for {st.full_name}.', 'success')
            return redirect(url_for(f'{bp_name}.student', body=body, student_id=sid, year=year))

        sid = request.args.get('student_id', type=int)
        year = request.args.get('year', type=int) or _default_year(svc.years_for(level, body))
        existing, cand = {}, None
        if sid and sid in allowed:
            existing = {r.subject: r for r in SchoolExamResult.query.filter_by(
                student_id=sid, level=level, body=body, exam_year=year).all()}
            cand = SchoolExamCandidate.query.filter_by(
                student_id=sid, level=level, body=body, exam_year=year).first()
        subjects = list(scheme.subjects) + [s for s in existing if s not in scheme.subjects]
        return render_template('school_exams/add_result.html', **_ctx(
            level, bp_name, body, students=students, student_id=sid, year=year,
            existing=existing, cand=cand, subjects=subjects))

    # ------------------------------------------------------------------ #
    # Grid entry (whole class at once)
    # ------------------------------------------------------------------ #
    @bp.route('/<body>/grid', methods=['GET', 'POST'])
    @login_required
    def grid_entry(body):
        _body_or_404(body)
        scheme = get_scheme(level, body)
        students = svc.level_students(level)
        year = (request.values.get('year', type=int)
                or _default_year(svc.years_for(level, body)))
        cols = request.values.getlist('col') or scheme.subjects[:9]
        cols = [c for c in cols if c]
        mode = request.values.get('mode', 'score')
        if request.method == 'POST':
            saved_students = saved_rows = 0
            for st in students:
                rows = []
                for i, subj in enumerate(cols):
                    v = (request.form.get(f'v_{st.id}_{i}') or '').strip()
                    if not v:
                        continue
                    rows.append((subj, None, v) if mode == 'grade' else (subj, v, None))
                exam_no = request.form.get(f'exam_number_{st.id}')
                total = request.form.get(f'total_{st.id}')
                cand = {}
                if exam_no is not None:
                    cand['exam_number'] = exam_no
                if total is not None:
                    cand['total_score'] = total
                if rows or any((v or '').strip() for v in cand.values()):
                    saved_rows += svc.save_student_results(scheme, st.id, year, rows, candidate=cand)
                    saved_students += 1
            db.session.commit()
            log_action(f'{bp_name}.grid_save', detail=f'{scheme.exam_name} {year}: '
                       f'{saved_students} student(s), {saved_rows} result(s)')
            flash(f'Saved {saved_rows} result(s) for {saved_students} candidate(s).', 'success')
            return redirect(url_for(f'{bp_name}.grid_entry', body=body, year=year, col=cols, mode=mode))

        ids = [s.id for s in students]
        existing = {}
        for r in SchoolExamResult.query.filter(
                SchoolExamResult.student_id.in_(ids or [-1]), SchoolExamResult.level == level,
                SchoolExamResult.body == body, SchoolExamResult.exam_year == year).all():
            existing[(r.student_id, r.subject)] = r
        cands = {c.student_id: c for c in SchoolExamCandidate.query.filter(
            SchoolExamCandidate.student_id.in_(ids or [-1]), SchoolExamCandidate.level == level,
            SchoolExamCandidate.body == body, SchoolExamCandidate.exam_year == year).all()}
        arms = svc.student_arm_map(level, ids)
        return render_template('school_exams/grid_entry.html', **_ctx(
            level, bp_name, body, students=students, year=year, cols=cols, mode=mode,
            existing=existing, cands=cands, arms=arms))

    # ------------------------------------------------------------------ #
    # Paste / CSV import
    # ------------------------------------------------------------------ #
    @bp.route('/<body>/import', methods=['GET', 'POST'])
    @login_required
    def import_results(body):
        _body_or_404(body)
        scheme = get_scheme(level, body)
        year = request.values.get('year', type=int) or _default_year(svc.years_for(level, body))
        text = request.form.get('data', '')
        preview = roster = None
        if request.method == 'POST':
            from utils import roster_placement as rp
            students = svc.level_students(level)
            rows, errors, subjects = svc.parse_import(scheme, text, students)
            roster = rp.plan(rows, level, year, students)
            ready = [r for r in rows if r.get('student') is not None
                     or (r.get('placement') == 'create' and not r.get('blocked'))]
            if request.form.get('action') == 'confirm' and ready:
                approved, include, arm_id, genders, use_existing = rp.approval_from_form(request.form)
                if (roster['creates'] or roster['moves']) and not approved:
                    flash('Tick "I approve" to add / move the listed students, then import.', 'error')
                else:
                    created, moved, _skipped = rp.apply(roster, include, arm_id, genders, use_existing)
                    n = cands = 0
                    for row in rows:
                        if row.get('student') is None:
                            continue
                        n += svc.save_student_results(scheme, row['student'].id, year,
                                                      row['subjects'], candidate=row['candidate'])
                        cands += 1
                    db.session.commit()
                    log_action(f'{bp_name}.import', detail=f'{scheme.exam_name} {year}: '
                               f'{cands} candidate(s), {n} result(s), {created} new student(s), '
                               f'{moved} moved to {L["class_label"]}')
                    flash(f'Imported {n} result(s) for {cands} candidate(s).'
                          + (f' Added {created} new student(s).' if created else '')
                          + (f' Moved {moved} student(s) into {L["class_label"]}.' if moved else ''),
                          'success')
                    return redirect(url_for(f'{bp_name}.dashboard', body=body, year=year))
            preview = {'rows': rows, 'errors': errors, 'subjects': subjects, 'n_ready': len(ready)}
        return render_template('school_exams/import.html', **_ctx(
            level, bp_name, body, year=year, text=text, preview=preview, roster=roster))

    # ------------------------------------------------------------------ #
    # Quick entry: "Name, Eng A, Maths B" — one line per candidate
    # ------------------------------------------------------------------ #
    @bp.route('/<body>/quick', methods=['GET', 'POST'])
    @login_required
    def quick_entry(body):
        from utils.quick_results import parse_quick_lines, school_exam_spec
        from utils import roster_placement as rp
        _body_or_404(body)
        scheme = get_scheme(level, body)
        year = request.values.get('year', type=int) or _default_year(svc.years_for(level, body))
        text = request.form.get('data', '')
        preview = roster = None
        if request.method == 'POST':
            students = svc.level_students(level)
            preview = parse_quick_lines(text, students,
                                        school_exam_spec(scheme, L['class_label']))
            roster = rp.plan(preview['rows'], level, year, students)
            rp.recount(preview)
            if request.form.get('action') == 'confirm' and preview['n_ready']:
                approved, include, arm_id, genders, use_existing = rp.approval_from_form(request.form)
                if (roster['creates'] or roster['moves']) and not approved:
                    flash('Tick "I approve" to add / move the listed students, then save.', 'error')
                else:
                    created, moved, _skipped = rp.apply(roster, include, arm_id, genders, use_existing)
                    saved = cands = 0
                    for row in preview['rows']:
                        if row.get('student') is None or not row['items']:
                            continue
                        saved += svc.save_student_results(
                            scheme, row['student'].id, year,
                            [(subj, score, grade) for subj, score, grade, _raw in row['items']])
                        cands += 1
                    db.session.commit()
                    log_action(f'{bp_name}.quick_entry', detail=f'{scheme.exam_name} {year}: '
                               f'{cands} candidate(s), {saved} result(s), {created} new student(s), '
                               f'{moved} moved to {L["class_label"]}')
                    flash(f'Saved {saved} {scheme.exam_name} result(s) for {cands} candidate(s).'
                          + (f' Added {created} new student(s).' if created else '')
                          + (f' Moved {moved} student(s) into {L["class_label"]}.' if moved else ''),
                          'success')
                    return redirect(url_for(f'{bp_name}.dashboard', body=body, year=year))
        return render_template('school_exams/quick.html', **_ctx(
            level, bp_name, body, year=year, text=text, preview=preview, roster=roster,
            roster_count=len(svc.level_students(level))))

    # ------------------------------------------------------------------ #
    # Student record
    # ------------------------------------------------------------------ #
    @bp.route('/<body>/student/<int:student_id>')
    @login_required
    def student(body, student_id):
        _body_or_404(body)
        st = _student_or_404(level, student_id)
        sittings = []
        for b in BODIES:
            scheme = get_scheme(level, b)
            years = sorted({r.exam_year for r in SchoolExamResult.query.filter_by(
                student_id=st.id, level=level, body=b).all()} |
                {c.exam_year for c in SchoolExamCandidate.query.filter_by(
                    student_id=st.id, level=level, body=b).all()}, reverse=True)
            for y in years:
                res, cands = svc.load(level, b, y)
                summ = svc.candidate_summaries(scheme, res, cands)
                me = next((s for s in summ if s['id'] == st.id), None)
                if me:
                    me['cohort'] = len(summ)
                    sittings.append({'body': b, 'year': y, 'scheme': scheme, 's': me,
                                     'name': scheme.exam_name})
        sittings.sort(key=lambda x: (x['body'] != body, -x['year']))
        return render_template('school_exams/student.html', **_ctx(
            level, bp_name, body, student=st, sittings=sittings,
            arm=svc.student_arm_map(level, [st.id]).get(st.id)))

    @bp.route('/<body>/student/<int:student_id>/<int:year>/delete', methods=['POST'])
    @login_required
    def delete_student_year(body, student_id, year):
        _body_or_404(body)
        st = _student_or_404(level, student_id)
        n = SchoolExamResult.query.filter_by(student_id=st.id, level=level, body=body,
                                             exam_year=year).delete()
        SchoolExamCandidate.query.filter_by(student_id=st.id, level=level, body=body,
                                            exam_year=year).delete()
        db.session.commit()
        log_action(f'{bp_name}.delete', detail=f'{body} {year}: {n} result(s)', target=st)
        flash(f'Deleted {n} result(s) for {st.full_name} ({year}).', 'success')
        return redirect(url_for(f'{bp_name}.dashboard', body=body, year=year))

    @bp.route('/<body>/delete-bulk', methods=['POST'])
    @login_required
    def delete_bulk(body):
        """Delete several candidates' results (and sitting records) for one
        exam body + year at once. Gated by the level's Delete permission."""
        from utils.branch_scope import can_access_branch
        _body_or_404(body)
        year = request.form.get('year', type=int)
        ids = set()
        for raw in request.form.getlist('ids'):
            try:
                ids.add(int(raw))
            except (TypeError, ValueError):
                pass
        students = [st for st in Student.query.filter(Student.id.in_(ids or [-1])).all()
                    if can_access_branch(st.branch_id)]
        if not year or not students:
            flash('Select at least one candidate to delete.', 'warning')
            return redirect(url_for(f'{bp_name}.dashboard', body=body, year=year))
        sids = [st.id for st in students]
        n = (SchoolExamResult.query.filter(SchoolExamResult.student_id.in_(sids),
                                           SchoolExamResult.level == level,
                                           SchoolExamResult.body == body,
                                           SchoolExamResult.exam_year == year)
             .delete(synchronize_session=False))
        SchoolExamCandidate.query.filter(SchoolExamCandidate.student_id.in_(sids),
                                         SchoolExamCandidate.level == level,
                                         SchoolExamCandidate.body == body,
                                         SchoolExamCandidate.exam_year == year
                                         ).delete(synchronize_session=False)
        db.session.commit()
        scheme = get_scheme(level, body)
        log_action(f'{bp_name}.delete_bulk', detail=f'{scheme.exam_name} {year}: '
                   f'{n} result(s), {len(sids)} candidate(s)')
        flash(f'Deleted {n} {scheme.exam_name} result(s) for {len(sids)} candidate(s) ({year}).',
              'success')
        return redirect(url_for(f'{bp_name}.dashboard', body=body, year=year))

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #
    @bp.route('/<body>/export')
    @login_required
    def export(body):
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from utils.web_exports import xlsx_response
        _body_or_404(body)
        years = svc.years_for(level, body)
        year = _default_year(years)
        stats = svc.year_stats(level, body, year)
        scheme = stats['scheme']
        subjects = [r['subject'] for r in sorted(stats['subjects'], key=lambda r: r['subject'])]
        wb = Workbook()
        ws = wb.active
        ws.title = f'{L["class_label"]} {body} {year}'[:31]
        ws.append([f'{scheme.exam_name} — {L["class_label"]} — {year}'])
        ws['A1'].font = Font(bold=True, size=14)
        head = (['Pos', 'Student', 'Exam No', 'Arm', 'Gender'] + subjects +
                ['Subjects', 'Distinctions', 'Credits', 'Passes', 'Fails', 'Avg %', 'Total',
                 'Eng+Maths credit', 'Meets benchmark', 'Placement', 'Admitted'])
        ws.append([])
        ws.append(head)
        fill = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')
        for c in ws[3]:
            c.font = Font(bold=True, color='FFFFFF')
            c.fill = fill
            c.alignment = Alignment(horizontal='center', wrap_text=True)
        for s in stats['candidates']:
            by = {r.subject: r for r in s['results']}
            cells = []
            for subj in subjects:
                r = by.get(subj)
                if r is None:
                    cells.append('')
                elif r.score is not None:
                    cells.append(f'{r.grade} ({r.score:g})')
                else:
                    cells.append(r.grade)
            ws.append([s['position'], s['name'], s['exam_number'] or '', s.get('arm') or '',
                       s['gender']] + cells +
                      [s['subjects'], s['distinctions'], s['credits'], s['passes'], s['fails'],
                       s['avg_pct'], s['total'], 'Yes' if s['core_credits'] else 'No',
                       'Yes' if s['meets_benchmark'] else 'No', s['placement'] or '',
                       {True: 'Yes', False: 'No'}.get(s['admitted'], '')])
        ws.column_dimensions['B'].width = 28
        # Subject analysis sheet
        ws2 = wb.create_sheet('Subject analysis')
        ws2.append(['Rank', 'Subject', 'Entries', 'Distinction %', 'Credit %', 'Pass %', 'Fail %',
                    'Mean %'] + scheme.grades)
        for c in ws2[1]:
            c.font = Font(bold=True)
        for r in stats['subjects']:
            ws2.append([r['rank'], r['subject'], r['entries'], r['distinction_rate'], r['credit_rate'],
                        r['pass_rate'], r['fail_rate'], r['mean_pct']] +
                       [r['grades'].get(g, 0) for g in scheme.grades])
        ws2.column_dimensions['B'].width = 30
        log_action('data.export_results', detail=f'{scheme.exam_name} {year}')
        return xlsx_response(wb, f'{level}_{body}_{year}.xlsx')

    # ------------------------------------------------------------------ #
    # Settings
    # ------------------------------------------------------------------ #
    @bp.route('/settings', methods=['GET', 'POST'])
    @login_required
    def settings():
        body = _body_or_404(request.values.get('body', 'state'))
        if request.method == 'POST':
            if request.form.get('action') == 'reset':
                from models.models_school_exams import SchoolExamConfig
                SchoolExamConfig.query.filter_by(level=level, body=body).delete()
                db.session.commit()
                flash('Settings reset to the defaults.', 'success')
                return redirect(url_for(f'{bp_name}.settings', body=body))
            ok, msg = svc.save_scheme(level, body, request.form)
            if ok:
                db.session.commit()
                log_action(f'{bp_name}.settings', detail=body)
                flash(msg, 'success')
            else:
                db.session.rollback()
                flash(msg, 'error')
            return redirect(url_for(f'{bp_name}.settings', body=body))
        return render_template('school_exams/settings.html', **_ctx(level, bp_name, body))

    return bp


jss3_exams_bp = make_blueprint('jss3')
basic6_exams_bp = make_blueprint('basic6')

exam_levels_bp = Blueprint('exam_levels', __name__, url_prefix='/exam-levels')


@exam_levels_bp.before_request
def _heal_levels():
    svc.ensure_school_exam_schema()


@exam_levels_bp.route('/')
@login_required
def index():
    """Level selector: SSS3 (WAEC/JAMB) · JSS3 (BECE) · Basic 6 (Common Entrance)."""
    from models import WAECResult, JAMBResult
    sss3 = {'waec': WAECResult.query.count(), 'jamb': JAMBResult.query.count()}
    levels = []
    for level in ('jss3', 'basic6'):
        cls = svc.find_level_class(level)
        levels.append({'meta': LEVEL_META[level], 'bp': f'{level}_exams',
                       'class_name': cls.name if cls else None,
                       'students': len(svc.level_students(level, include_with_results=False)),
                       'overview': svc.level_overview(level)})
    return render_template('school_exams/levels.html', levels=levels, sss3=sss3)
