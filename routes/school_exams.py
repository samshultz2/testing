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
from utils.security import rate_limited
from utils import school_exams as svc


class _LiveMeta(dict):
    """LEVEL_META for a level, with the Common Entrance class label / name
    following the school's setting (Basic 6, Basic 5, or Basic 5 / 6)."""

    def __init__(self, level):
        super().__init__(LEVEL_META[level])
        self.level = level

    def __getitem__(self, key):
        if self.level == 'basic6' and key in ('class_label', 'name', 'long_name'):
            lab = svc.level_class_label('basic6')
            return {'class_label': lab, 'name': f'{lab} Exams',
                    'long_name': f'Primary / {lab} — Common Entrance Examination'}[key]
        return super().__getitem__(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default


def _default_year(years):
    from utils.helpers import resolve_exam_year
    return resolve_exam_year(request.args.get('year', type=int), years) or _date.today().year


def _body_or_404(body):
    if body not in BODIES:
        abort(404)
    return body


def _ctx(level, bp_name, body=None, **extra):
    L = _LiveMeta(level)
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


def _branded_export(level, body, year, stats, fmt):
    """Branded PDF / image / Word results document (Students List or Subject
    Analysis) — the same design as the WAEC / NECO export, graded on this
    exam's own scale."""
    from utils.access_control import get_current_user
    from utils.school import school_profile, document_branding
    from utils.student_list_export import colors_for
    from utils import exam_results_doc as ERD

    etype = 'subjects' if request.args.get('type') == 'subjects' else 'students'
    cols = set((request.args.get('cols') or '').split(',')) - {''}
    u = get_current_user()
    L = _LiveMeta(level)
    ctx = {'school': school_profile(), 'colors': colors_for(document_branding()),
           'prepared_by': (getattr(u, 'full_name', None) or getattr(u, 'username', None) or '') if u else '',
           'tag': 'EXAM RESULTS', 'cls': L['class_label'], 'detail': body.title()}
    doc = svc.export_doc(level, body, year, stats, etype, cols, ctx)
    stem = '%s_%s_%s_%s' % (level, body, 'subject_analysis' if etype == 'subjects' else 'results', year)
    return ERD.file_response(doc, fmt, stem)


def make_blueprint(level):
    bp_name = f'{level}_exams'
    bp = Blueprint(bp_name, __name__, url_prefix=f'/{level}-exams')
    L = _LiveMeta(level)

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
        # WAEC-style filters: subject / grade / minimum distinctions & credits.
        f_subject = (request.args.get('subject') or '').strip()
        f_grade = (request.args.get('grade') or '').strip()
        min_d = request.args.get('min_d', type=int)
        min_c = request.args.get('min_c', type=int)
        cands = svc.filter_candidates(cands, f_subject, f_grade, min_d, min_c)
        cands, sort = svc.sort_candidates(cands, request.args.get('sort', 'position'))
        view = request.args.get('view', 'students')
        if view not in ('students', 'subjects', 'top'):
            view = 'students'
        subjects, ssort = svc.sort_subjects(stats['subjects'], request.args.get('ssort'))
        other = 'federal' if body == 'state' else 'state'
        return render_template('school_exams/dashboard.html', **_ctx(
            level, bp_name, body, years=years, year=year, stats=stats,
            candidates=cands, search=search, other=other, sort=sort,
            sorts=[(k, v[0]) for k, v in svc.CANDIDATE_SORTS.items()],
            other_years=svc.years_for(level, other),
            trend=svc.trend(level, body),
            view=view, f_subject=f_subject, f_grade=f_grade, min_d=min_d, min_c=min_c,
            filtered=bool(f_subject or f_grade or min_d or min_c or search),
            subject_names=sorted(r['subject'] for r in stats['subjects']),
            subjects_sorted=subjects, ssort=ssort, subject_sorts=svc.subject_sorts(stats['scheme']),
            top_grades=svc.top_by_grade(stats['scheme'], stats['candidates']),
            export_cols=svc.export_columns(stats['scheme'])))

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
        # Only offer students still without results for this exam + year; the
        # student opened via an Edit link stays so their results can be changed.
        done = svc.entered_ids(level, body, year, allowed)
        pick = [s for s in students if s.id not in done or s.id == sid]
        return render_template('school_exams/add_result.html', **_ctx(
            level, bp_name, body, students=pick, student_id=sid, year=year,
            existing=existing, cand=cand, subjects=subjects,
            hidden_entered=len(done - {sid}), roster_total=len(students)))

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
            return redirect(url_for(f'{bp_name}.grid_entry', body=body, year=year, col=cols, mode=mode,
                                    show=request.values.get('show') or None))

        # Students who already have results for this exam + year are hidden
        # unless ?show=all (to correct them in the grid).
        show_all = request.args.get('show') == 'all'
        done = svc.entered_ids(level, body, year, [s.id for s in students])
        hidden_entered = 0 if show_all else len(done)
        if not show_all:
            students = [s for s in students if s.id not in done]
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
            existing=existing, cands=cands, arms=arms, show_all=show_all,
            hidden_entered=hidden_entered, entered_total=len(done)))

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

    @bp.route('/compare/export')
    @login_required
    @rate_limited('export', max_requests=40, window_minutes=10)
    def compare_export():
        """State vs Federal comparison as a branded PDF or image (PNG pages)."""
        from utils.access_control import get_current_user
        from utils.school import school_profile, document_branding
        from utils.student_list_export import colors_for
        from utils import exam_results_doc as ERD
        from utils.exam_compare_doc import compare_doc
        fmt = request.args.get('format', 'pdf')
        if fmt not in ('pdf', 'image'):
            abort(400)
        years = sorted(set(svc.years_for(level, 'state')) | set(svc.years_for(level, 'federal')),
                       reverse=True)
        year = _default_year(years)
        u = get_current_user()
        ctx = {'school': school_profile(), 'colors': colors_for(document_branding()),
               'prepared_by': (getattr(u, 'full_name', None) or getattr(u, 'username', None) or '') if u else ''}
        doc = compare_doc(level, year, ctx)
        return ERD.file_response(doc, fmt, '%s_state_vs_federal_%s' % (level, year))

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #
    @bp.route('/<body>/export')
    @login_required
    @rate_limited('export', max_requests=40, window_minutes=10)
    def export(body):
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from utils.web_exports import xlsx_response
        _body_or_404(body)
        years = svc.years_for(level, body)
        year = _default_year(years)
        stats = svc.year_stats(level, body, year)
        scheme = stats['scheme']
        fmt = request.args.get('format', 'excel')
        if fmt in ('pdf', 'image', 'word'):
            log_action('data.export_results', detail=f'{scheme.exam_name} {year} ({fmt})')
            return _branded_export(level, body, year, stats, fmt)
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
    # Broadsheet — same pattern as the WAEC broadsheet (page + print PDF with
    # paper sizes + custom download in PDF / image / Excel / CSV)
    # ------------------------------------------------------------------ #
    def _bs_args(body):
        years = svc.years_for(level, body)
        year = _default_year(years)
        arms = [a for a in (request.args.get('arms') or '').split(',') if a.strip()]
        subjects = [x for x in (request.args.get('subjects') or '').split(',') if x.strip()]
        order = 'position' if request.args.get('order') == 'position' else 'name'
        return years, year, svc.broadsheet(level, body, year, arms=arms, subjects=subjects, order=order)

    def _bs_titles(body, year, bs):
        scheme = bs['scheme']
        heading = f'{scheme.exam_name} {year} — {L["class_label"]} Broadsheet'
        return heading, scheme

    @bp.route('/<body>/broadsheet')
    @login_required
    def broadsheet(body):
        _body_or_404(body)
        years, year, bs = _bs_args(body)
        return render_template('school_exams/broadsheet.html', **_ctx(
            level, bp_name, body, years=years, year=year, bs=bs))

    @bp.route('/<body>/broadsheet.pdf')
    @login_required
    @rate_limited('export', max_requests=40, window_minutes=10)
    def broadsheet_pdf(body):
        """Print-ready broadsheet PDF (A4 / A3 / A2, landscape or portrait,
        columns per sheet). Previews inline; ?download=1 to save."""
        from flask import send_file
        from utils.school import school_profile, logo_path
        from utils.waec_broadsheet_pdf import waec_broadsheet_pdf as _mk
        from utils.name_display import name_opts
        _body_or_404(body)
        _years, year, bs = _bs_args(body)
        if not bs['rows']:
            flash('No results recorded for that year.', 'warning')
            return redirect(url_for(f'{bp_name}.broadsheet', body=body, year=year))
        heading, scheme = _bs_titles(body, year, bs)
        size = request.args.get('size', 'A4').upper()
        school = dict(school_profile() or {})
        school.setdefault('logo_path', logo_path())
        per = request.args.get('cols', default=0, type=int)
        buf = _mk(bs, year, school, opts={'title': False, 'name_fmt': name_opts(request.args)},
                  per=(per if per and per > 0 else 0), orient=request.args.get('orient', 'landscape'),
                  size=(size if size in ('A4', 'A3', 'A2') else 'A4'), heading=heading,
                  tail_labels=('Credits', 'Avg %'),
                  summary_labels=('No. offered', 'No. passed', 'No. failed', 'Average %'),
                  grade_key=False)
        log_action('data.export_results', detail=f'{scheme.exam_name} {year} broadsheet PDF')
        return send_file(buf, mimetype='application/pdf',
                         as_attachment=request.args.get('download') == '1',
                         download_name=f'{level}_{body}_broadsheet_{year}.pdf')

    @bp.route('/<body>/broadsheet/download')
    @login_required
    @rate_limited('export', max_requests=40, window_minutes=10)
    def broadsheet_download(body):
        """Custom broadsheet download: arms, subjects, heading, names and
        order chosen in the page's "Custom download" box; format = pdf |
        image | excel | csv (same as the WAEC broadsheet)."""
        from flask import Response
        from utils import broadsheet_export as bx
        from utils.name_display import name_opts, format_name
        from utils.school import logo_path as _logo_path, school_profile as _school_profile
        from utils.web_exports import xlsx_response, formula_guard
        _body_or_404(body)
        _years, year, bs = _bs_args(body)
        if not bs['rows']:
            flash('No candidates match the selection for that year.', 'warning')
            return redirect(url_for(f'{bp_name}.broadsheet', body=body, year=year))
        heading, scheme = _bs_titles(body, year, bs)
        title = (request.args.get('title') or '').strip()[:120] or heading
        arms = request.args.get('arms') or ''
        subtitle = (f'{scheme.exam_name} {year} · {arms.replace(",", ", ") or "All arms"} · '
                    f'{len(bs["rows"])} candidate(s)')
        nfmt = name_opts(request.args)
        subjects = bs['subjects']
        full_headers = ['S/N', 'Candidate'] + subjects + ['Credits', 'Avg %']
        full_rows = []
        for i, r in enumerate(bs['rows'], 1):
            line = [str(i), formula_guard(format_name(r['student'], nfmt))]
            line += [r['cells'].get(subj, '–') for subj in subjects]
            line += [str(r['credits']), r['avg_grade'] or '–']
            full_rows.append(line)
        fname = f'{level}_{body}_broadsheet_{year}'
        fmt = (request.args.get('format') or 'pdf').lower()
        log_action('data.export_results', detail=f'{scheme.exam_name} {year} broadsheet ({fmt})')
        if fmt in ('excel', 'xlsx'):
            return xlsx_response(bx.combo_xlsx(full_headers, full_rows, title, subtitle), f'{fname}.xlsx')
        if fmt == 'csv':
            import csv as _csv
            from io import StringIO
            buf = StringIO(); w = _csv.writer(buf); w.writerow(full_headers)
            for dr in full_rows:
                w.writerow(dr)
            return Response(buf.getvalue(), mimetype='text/csv', headers={
                'Content-Disposition': f'attachment; filename="{fname}.csv"'})
        codes, legend = bx.abbreviate_subjects(subjects)
        headers = ['S/N', 'Candidate'] + codes + ['Cred', 'Avg']
        lp, sname = _logo_path(), (_school_profile() or {}).get('name') or None
        if fmt in ('image', 'png'):
            pages = bx.combo_png_pages(headers, full_rows, title, subtitle, legend=legend,
                                       logo_path=lp, school_name=sname)
            page = max(1, min(request.args.get('page', type=int) or 1, len(pages)))
            suffix = '' if len(pages) == 1 else f'_p{page}'
            return Response(pages[page - 1], mimetype='image/png', headers={
                'Content-Disposition': f'attachment; filename="{fname}{suffix}.png"',
                'X-Total-Pages': str(len(pages)), 'Access-Control-Expose-Headers': 'X-Total-Pages'})
        data = bx.combo_pdf(headers, full_rows, title, subtitle, numeric_from=2, legend=legend,
                            logo_path=lp, school_name=sname)
        return Response(data, mimetype='application/pdf', headers={
            'Content-Disposition': f'attachment; filename="{fname}.pdf"'})

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
            if level == 'basic6' and request.form.get('ce_classes') in svc.CE_CHOICES:
                from models import SchoolSettings
                SchoolSettings.set(svc.CE_SETTING_KEY, request.form['ce_classes'],
                                   description='Class(es) that sit Common Entrance')
            ok, msg = svc.save_scheme(level, body, request.form)
            if ok:
                db.session.commit()
                log_action(f'{bp_name}.settings', detail=body)
                flash(msg, 'success')
            else:
                db.session.rollback()
                flash(msg, 'error')
            return redirect(url_for(f'{bp_name}.settings', body=body))
        return render_template('school_exams/settings.html', **_ctx(
            level, bp_name, body, ce_choices=svc.CE_CHOICES, ce_value=svc.ce_classes_setting()))

    return bp


jss3_exams_bp = make_blueprint('jss3')
basic6_exams_bp = make_blueprint('basic6')

exam_levels_bp = Blueprint('exam_levels', __name__, url_prefix='/exam-levels')


@exam_levels_bp.app_context_processor
def _ce_nav():
    """``ce_exams_label()`` for the sidebar: "Basic 6 Exams", "Basic 5 Exams"
    or "Basic 5 / 6 Exams" — a callable, so pages that don't show the
    sidebar never query the setting."""
    def ce_exams_label():
        try:
            return f"{svc.level_class_label('basic6')} Exams"
        except Exception:
            return 'Basic 6 Exams'
    return {'ce_exams_label': ce_exams_label}


@exam_levels_bp.before_request
def _heal_levels():
    svc.ensure_school_exam_schema()


@exam_levels_bp.route('/')
@login_required
def index():
    """External exams hub: every public exam by class level (SSS3 · JSS3 ·
    Basic 5/6) with the latest year, the change since the one before and
    what needs attention. Branch-scoped to the branch being viewed."""
    from utils.branch_scope import viewing_branch_id
    from utils import exam_levels_overview as XO
    data = XO.build(_LiveMeta, viewing_branch_id())
    return render_template('school_exams/levels.html', hub=data)
