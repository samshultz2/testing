"""Bulk import of WAEC / NECO / JAMB results from Excel, CSV or pasted cells.

Two steps: ``analyse`` reads the sheet and says, row by row, what would
happen (new / update / unchanged / problem) without touching the database;
``apply`` re-reads the same sheet and saves only the rows that passed.

Accepted layouts
  WAEC / NECO, long:  student_id, exam_year, subject, grade   (one row per subject)
  WAEC / NECO, wide:  student_id, exam_year, <Subject>, <Subject> …  (one row per student)
  JAMB:               student_id, exam_year, total_score, subject1, subject1_score … subject4_score
Header names are forgiving ("Admission No", "Year", "Total" …). Students are
matched by admission number within the branches the user can see; a name is
accepted only when exactly one visible student has it.
"""
import csv
import io
import re

from utils.exam_rules import WAEC_GRADES, canonical_subject, norm_grade

EXAMS = ('waec', 'neco', 'jamb')

ID_KEYS = ('student_id', 'admission_no', 'admission_number', 'admission', 'adm_no', 'id', 'student',
           'student_no', 'reg_no', 'code', 'student_code')
NAME_KEYS = ('name', 'full_name', 'student_name', 'candidate', 'candidate_name')
YEAR_KEYS = ('exam_year', 'year', 'session', 'exam_session')
SUBJECT_KEYS = ('subject', 'subject_name')
GRADE_KEYS = ('grade', 'result')
TOTAL_KEYS = ('total_score', 'total', 'score', 'aggregate', 'utme_score')
SKIP_WIDE = set(ID_KEYS + NAME_KEYS + YEAR_KEYS + ('s/n', 'sn', 's_n', 'no', 'serial', 'class', 'arm',
                                                   'gender', 'sex', 'exam_number', 'exam_no', 'reg_number', 'remark', 'remarks',
                                                   'total', 'position', 'credits', 'comment', 'pin', 'serial_number'))


def _key(h):
    return re.sub(r'[^a-z0-9/]+', '_', str(h or '').strip().lower()).strip('_')


def _blank(v):
    if v is None:
        return True
    s = str(v).strip()
    return s == '' or s.lower() in ('nan', 'none', 'null', '-')


def _text(v):
    if _blank(v):
        return ''
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def read_table(file=None, text=None):
    """(headers, rows) from an uploaded .xlsx/.xls/.csv or pasted text.
    rows: list of (line_number, {header_key: value})."""
    raw = []
    if file is not None and getattr(file, 'filename', ''):
        name = file.filename.lower()
        data = file.read()
        if name.endswith(('.xlsx', '.xlsm', '.xls')):
            from openpyxl import load_workbook
            try:
                wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            except Exception as e:
                raise ValueError(f'Could not open that spreadsheet ({e}). Save it as .xlsx or .csv and try again.')
            ws = wb.active
            raw = [list(r) for r in ws.iter_rows(values_only=True)]
        else:
            txt = data.decode('utf-8-sig', errors='replace')
            raw = list(csv.reader(io.StringIO(txt), dialect=_sniff(txt)))
    elif text and text.strip():
        raw = list(csv.reader(io.StringIO(text.strip()), dialect=_sniff(text)))
    # Skip leading empty rows / titles until a row that looks like a header.
    while raw and sum(1 for c in raw[0] if not _blank(c)) < 2:
        raw.pop(0)
    if not raw:
        raise ValueError('The sheet is empty.')
    headers = [_key(h) for h in raw[0]]
    rows = []
    for i, r in enumerate(raw[1:], start=2):
        if all(_blank(c) for c in r):
            continue
        rows.append((i, {headers[j]: r[j] for j in range(min(len(headers), len(r))) if headers[j]}))
    return headers, rows


def _sniff(txt):
    sample = txt[:2000]
    if '\t' in sample:
        class T(csv.excel_tab):
            pass
        return T
    return csv.excel


def _first(row, keys):
    for k in keys:
        if k in row and not _blank(row[k]):
            return row[k]
    return None


class _Students:
    """Lookup of the students the current user may see."""

    def __init__(self):
        from models import Student
        from utils.branch_scope import scope_query
        studs = scope_query(Student.query, Student).all()
        self.by_code = {s.student_id.strip().lower(): s for s in studs if s.student_id}
        self.by_name = {}
        for s in studs:
            for nm in {s.full_name, f'{s.first_name} {s.surname}'}:
                self.by_name.setdefault(re.sub(r'\s+', ' ', (nm or '').strip().lower()), []).append(s)

    def find(self, code, name):
        if code:
            s = self.by_code.get(_text(code).lower())
            if s:
                return s, None
        if name:
            hits = {x.id: x for x in self.by_name.get(re.sub(r'\s+', ' ', _text(name).lower()), [])}
            if len(hits) == 1:
                return next(iter(hits.values())), 'matched by name'
            if len(hits) > 1:
                return None, f'{len(hits)} students are called "{_text(name)}" — use the admission number'
        if code and not name:
            hits = {x.id: x for x in self.by_name.get(re.sub(r'\s+', ' ', _text(code).lower()), [])}
            if len(hits) == 1:
                return next(iter(hits.values())), 'matched by name'
        return None, f'No student "{_text(code) or _text(name)}" in your school' if (code or name) else 'No admission number'


def _year(v, default):
    t = _text(v)
    if not t:
        return default, None if default else 'No exam year'
    m = re.search(r'(20\d\d)(?!.*20\d\d)', t)     # "2024/2025" -> 2025
    if not m:
        return None, f'Exam year "{t}" is not a year'
    return int(m.group(1)), None


def analyse(exam, headers, rows, default_year=None):
    """Row-by-row verdicts without saving. Returns
    {'rows': [...], 'counts': {...}, 'layout': 'long'|'wide'|'jamb'}."""
    exam = exam if exam in EXAMS else 'waec'
    look = _Students()
    model = _model(exam)
    out = []
    if exam == 'jamb':
        layout = 'jamb'
    else:
        layout = 'long' if any(k in headers for k in SUBJECT_KEYS) and any(k in headers for k in GRADE_KEYS) else 'wide'
    wide_cols = [h for h in headers if h and h not in SKIP_WIDE] if layout == 'wide' else []
    head_label = {}
    for h in wide_cols:
        head_label[h] = canonical_subject(h.replace('_', ' ').title()) or h.replace('_', ' ').title()

    for line, r in rows:
        problems, notes = [], []
        stu, why = look.find(_first(r, ID_KEYS), _first(r, NAME_KEYS))
        if not stu:
            problems.append(why)
        elif why:
            notes.append(why)
        year, yerr = _year(_first(r, YEAR_KEYS), default_year)
        if yerr:
            problems.append(yerr)
        items = []
        if exam == 'jamb':
            subs = []
            for n in range(1, 5):
                nm = _text(r.get(f'subject{n}') or r.get(f'subject_{n}'))
                sc = _text(r.get(f'subject{n}_score') or r.get(f'subject_{n}_score') or r.get(f'score{n}'))
                if not nm and not sc:
                    continue
                if not nm:
                    problems.append(f'Subject {n} has a score but no name')
                    continue
                score = None
                if sc:
                    try:
                        score = int(float(sc))
                    except ValueError:
                        problems.append(f'{nm}: "{sc}" is not a score')
                        continue
                    if not 0 <= score <= 100:
                        problems.append(f'{nm}: {score} is not between 0 and 100')
                        continue
                subs.append((canonical_subject(nm) or nm, score))
            tot = _text(_first(r, TOTAL_KEYS))
            total = None
            if tot:
                try:
                    total = int(float(tot))
                except ValueError:
                    problems.append(f'Total "{tot}" is not a number')
            elif len(subs) == 4 and all(s is not None for _, s in subs):
                total = sum(s for _, s in subs)
            if total is None and not problems:
                problems.append('No total score')
            elif total is not None and not 0 <= total <= 400:
                problems.append(f'Total {total} is not between 0 and 400')
            items = [{'subject': n, 'value': s} for n, s in subs]
            row = {'line': line, 'total': total, 'items': items}
        else:
            pairs = []
            if layout == 'long':
                pairs = [(_text(_first(r, SUBJECT_KEYS)), _text(_first(r, GRADE_KEYS)))]
            else:
                pairs = [(head_label[h], _text(r.get(h))) for h in wide_cols if _text(r.get(h))]
            if not pairs or not any(p[0] or p[1] for p in pairs):
                problems.append('No subject or grade')
            for subj, g in pairs:
                if not subj:
                    problems.append('A grade has no subject')
                    continue
                gg = norm_grade(g).replace(' ', '')
                if gg in ('ABS', 'AB', 'ABSENT', 'X'):
                    notes.append(f'{subj}: absent — skipped')
                    continue
                if gg not in WAEC_GRADES:
                    problems.append(f'{subj}: "{g}" is not a grade (A1…F9)' if g else f'{subj}: no grade')
                    continue
                items.append({'subject': canonical_subject(subj) or subj, 'value': gg})
            row = {'line': line, 'items': items}
        row.update({
            'student': ({'id': stu.id, 'name': stu.full_name, 'code': stu.student_id} if stu else None),
            'year': year, 'problems': problems, 'notes': notes,
        })
        row['status'] = 'error' if problems else _status(exam, model, stu, year, row)
        out.append(row)

    # The same subject twice for one student/year in this sheet, with different grades.
    if exam != 'jamb':
        seen = {}
        for row in out:
            if row['status'] == 'error':
                continue
            for it in row['items']:
                k = (row['student']['id'], row['year'], it['subject'].lower())
                prev = seen.get(k)
                if prev and prev[0] != it['value']:
                    row['problems'].append(f'{it["subject"]} is also on row {prev[1]} with a different grade')
                    row['status'] = 'error'
                seen.setdefault(k, (it['value'], row['line']))
    counts = {s: sum(1 for r in out if r['status'] == s) for s in ('new', 'update', 'same', 'error')}
    counts['rows'] = len(out)
    counts['results'] = sum(len(r['items']) or (1 if exam == 'jamb' else 0) for r in out if r['status'] in ('new', 'update'))
    return {'rows': out, 'counts': counts, 'layout': layout}


def _model(exam):
    from models import WAECResult, JAMBResult
    if exam == 'jamb':
        return JAMBResult
    if exam == 'neco':
        from models import NECOResult
        return NECOResult
    return WAECResult


def _status(exam, model, stu, year, row):
    if exam == 'jamb':
        ex = model.query.filter_by(student_id=stu.id, exam_year=year).first()
        if not ex:
            return 'new'
        same = ex.total_score == row['total'] and all(
            (getattr(ex, f'subject{n}') or '') == (row['items'][n - 1]['subject'] if n <= len(row['items']) else (getattr(ex, f'subject{n}') or ''))
            for n in range(1, 5))
        return 'same' if same else 'update'
    have = {r.subject.lower(): r.grade for r in model.query.filter_by(student_id=stu.id, exam_year=year).all()}
    for it in row['items']:
        was = have.get(it['subject'].lower())
        if was and was != it['value']:
            it['was'] = was
    if not row['items']:
        return 'same'
    if all(have.get(it['subject'].lower()) == it['value'] for it in row['items']):
        return 'same'
    return 'update' if any(it['subject'].lower() in have for it in row['items']) else 'new'


def apply(exam, analysis):
    """Save every row that passed. Returns (added, updated). Caller commits."""
    from models import db
    model = _model(exam)
    added = updated = 0
    for row in analysis['rows']:
        if row['status'] not in ('new', 'update'):
            continue
        sid, year = row['student']['id'], row['year']
        if exam == 'jamb':
            obj = model.query.filter_by(student_id=sid, exam_year=year).first()
            if obj:
                updated += 1
            else:
                obj = model(student_id=sid, exam_year=year, total_score=row['total'])
                db.session.add(obj)
                added += 1
            obj.total_score = row['total']
            for n, it in enumerate(row['items'][:4], start=1):
                setattr(obj, f'subject{n}', it['subject'])
                setattr(obj, f'subject{n}_score', it['value'])
            continue
        have = {r.subject.lower(): r for r in model.query.filter_by(student_id=sid, exam_year=year).all()}
        for it in row['items']:
            ex = have.get(it['subject'].lower())
            if ex:
                if ex.grade != it['value']:
                    ex.grade = it['value']
                    updated += 1
            else:
                r = model(student_id=sid, exam_year=year, subject=it['subject'], grade=it['value'])
                db.session.add(r)
                have[it['subject'].lower()] = r
                added += 1
    return added, updated
