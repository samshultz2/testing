"""results blueprint — imports routes (split from the former routes/results.py)."""
from routes.results import *  # noqa: F401,F403


@results_bp.route('/import')
@login_required
def import_results():
    from utils.helpers import exam_year_choices
    exam = request.args.get('exam') if request.args.get('exam') in ('waec', 'neco', 'jamb') else 'waec'
    years = exam_year_choices()
    return render_template('results/import_results.html', exam=exam, years=years,
                           default_year=max(years) if years else None)


@results_bp.route('/import/template/<exam>')
@login_required
def import_template(exam):
    from openpyxl import Workbook
    from io import BytesIO
    wb = Workbook()
    ws = wb.active
    if exam == 'jamb':
        ws.title = 'JAMB'
        ws.append(['student_id', 'exam_year', 'total_score', 'subject1', 'subject1_score',
                   'subject2', 'subject2_score', 'subject3', 'subject3_score', 'subject4', 'subject4_score'])
        ws.append(['STU00001', 2025, 250, 'English Language', 62, 'Mathematics', 70, 'Physics', 60, 'Chemistry', 58])
        fn = 'jamb_import_template.xlsx'
    elif request.args.get('layout') == 'wide':
        ws.title = exam.upper()
        ws.append(['student_id', 'exam_year', 'English Language', 'Mathematics', 'Biology', 'Physics', 'Chemistry'])
        ws.append(['STU00001', 2025, 'C4', 'B2', 'B3', 'C5', 'C6'])
        fn = f'{exam}_import_template_one_row_per_student.xlsx'
    else:
        ws.title = 'NECO' if exam == 'neco' else 'WAEC'
        ws.append(['student_id', 'exam_year', 'subject', 'grade'])
        ws.append(['STU00001', 2025, 'Mathematics', 'B2'])
        ws.append(['STU00001', 2025, 'English Language', 'C4'])
        fn = f'{"neco" if exam == "neco" else "waec"}_import_template.xlsx'
    return xlsx_response(wb, fn)


@results_bp.route('/import/<exam>', methods=['POST'])
@login_required
def import_results_run(exam):
    """mode=preview: say what each row would do (JSON, nothing saved).
    mode=apply (default): save the rows that pass; problem rows are skipped.
    Answers JSON to the page's fetch, else flashes and redirects (old form)."""
    from utils import results_import as RI
    from routes.results.entry import wants_fetch
    exam = exam if exam in RI.EXAMS else 'waec'
    mode = request.form.get('mode', 'apply')
    js = wants_fetch()
    back = url_for('results.import_results', exam=exam)
    try:
        headers, rows = RI.read_table(request.files.get('file'), request.form.get('text'))
        if len(rows) > 5000:
            raise ValueError('That sheet has more than 5,000 rows — split it into smaller files.')
        result = RI.analyse(exam, headers, rows, default_year=request.form.get('year', type=int))
    except ValueError as e:
        if js:
            return jsonify({'ok': False, 'error': str(e)}), 400
        flash(str(e), 'error')
        return redirect(back)
    except Exception as e:  # pragma: no cover - unreadable file
        current_app.logger.exception('results import failed to read')
        if js:
            return jsonify({'ok': False, 'error': f'Could not read the file: {e}'}), 400
        flash(f'Could not read the file: {e}', 'error')
        return redirect(back)
    if mode == 'preview':
        return jsonify({'ok': True, 'exam': exam, **result})
    added, updated = RI.apply(exam, result)
    db.session.commit()
    c = result['counts']
    log_action(f'import_{exam}', f'{added} added, {updated} updated, {c["error"]} row(s) skipped')
    try:
        from routes.results import bust_school_stats
        bust_school_stats()
    except Exception:
        pass
    links = {'waec': url_for('results.waec_list'), 'jamb': url_for('results.jamb_list')}
    try:
        links['neco'] = url_for('results.neco_list')
    except Exception:
        links['neco'] = links['waec']
    if js:
        return jsonify({'ok': True, 'added': added, 'updated': updated, 'skipped': c['error'],
                        'same': c['same'], 'view_url': links.get(exam)})
    flash(f'{exam.upper()} import: {added} added, {updated} updated'
          + (f', {c["error"]} row(s) skipped because of problems' if c['error'] else '') + '.',
          'success' if (added or updated) else 'warning')
    for r in [r for r in result['rows'] if r['problems']][:8]:
        flash(f'Row {r["line"]}: {"; ".join(r["problems"])}', 'error')
    return redirect(back)
