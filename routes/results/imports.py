"""results blueprint — imports routes (split from the former routes/results.py)."""
from routes.results import *  # noqa: F401,F403


@results_bp.route('/import')
@login_required
def import_results():
    return render_template('results/import_results.html')


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
    else:
        ws.title = 'WAEC'
        ws.append(['student_id', 'exam_year', 'subject', 'grade'])
        ws.append(['STU00001', 2025, 'Mathematics', 'B2'])
        ws.append(['STU00001', 2025, 'English Language', 'C4'])
        fn = 'waec_import_template.xlsx'
    return xlsx_response(wb, fn)


@results_bp.route('/import/<exam>', methods=['POST'])
@login_required
def import_results_run(exam):
    import pandas as pd
    exam = 'jamb' if exam == 'jamb' else 'waec'
    file = request.files.get('file')
    if not file or not file.filename:
        flash('Please choose a file.', 'error')
        return redirect(url_for('results.import_results'))

    try:
        name = file.filename.lower()
        df = pd.read_csv(file) if name.endswith('.csv') else pd.read_excel(file)
    except Exception as e:
        flash(f'Could not read the file: {e}', 'error')
        return redirect(url_for('results.import_results'))

    df.columns = [str(c).strip().lower() for c in df.columns]

    students = Student.query.all()
    by_code = {s.student_id.lower(): s for s in students if s.student_id}
    by_name = {s.full_name.lower(): s for s in students}

    def find_student(val):
        v = str(val).strip().lower()
        return by_code.get(v) or by_name.get(v)

    imported, skipped, errors = 0, 0, []
    for i, row in df.iterrows():
        line = i + 2  # header is row 1
        try:
            stu = find_student(row.get('student_id'))
            if not stu:
                skipped += 1
                errors.append(f'Row {line}: student "{row.get("student_id")}" not found')
                continue
            year = int(row.get('exam_year'))
            if exam == 'waec':
                subject = str(row.get('subject') or '').strip()
                grade = str(row.get('grade') or '').strip().upper()
                if not subject or not grade:
                    skipped += 1
                    continue
                existing = WAECResult.query.filter_by(student_id=stu.id, exam_year=year, subject=subject).first()
                if existing:
                    existing.grade = grade
                else:
                    db.session.add(WAECResult(student_id=stu.id, exam_year=year, subject=subject, grade=grade))
                imported += 1
            else:
                total = int(row.get('total_score') or 0)
                existing = JAMBResult.query.filter_by(student_id=stu.id, exam_year=year).first()
                obj = existing or JAMBResult(student_id=stu.id, exam_year=year, total_score=total)
                obj.total_score = total
                for n in range(1, 5):
                    sname = row.get(f'subject{n}')
                    sscore = row.get(f'subject{n}_score')
                    if pd.notna(sname):
                        setattr(obj, f'subject{n}', str(sname).strip())
                        setattr(obj, f'subject{n}_score', int(sscore) if pd.notna(sscore) else None)
                if not existing:
                    db.session.add(obj)
                imported += 1
        except Exception as e:
            skipped += 1
            errors.append(f'Row {line}: {e}')

    db.session.commit()
    log_action(f'import_{exam}', f'{imported} imported, {skipped} skipped')
    flash(f'{exam.upper()} import complete: {imported} saved, {skipped} skipped.',
          'success' if imported else 'warning')
    for e in errors[:8]:
        flash(e, 'error')
    return redirect(url_for('results.import_results'))
