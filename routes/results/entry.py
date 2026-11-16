"""Fast result entry for SSS3 external exams — many students at once (a
keyboard grid on laptops, one-student-at-a-time sheets on phones) or one
student — for JAMB (scores /100 per subject, total /400) and WAEC / NECO
(a grade A1…F9 per subject). The add pages render the shell; the React entry
app posts here as fetch requests and gets JSON back."""
from routes.results import *  # noqa: F401,F403
from utils import exam_board as _board
from utils.helpers import WAEC_GRADES, WAEC_DEFAULT_SUBJECTS, exam_year_choices

WAEC_SLOTS = 9          # WASSCE / SSCE: up to nine subjects per candidate
JAMB_SUBJECTS = 4       # UTME: English + three subjects, each /100


def wants_fetch():
    return request.headers.get('X-Requested-With') == 'fetch'


def _sessions(year):
    ch = exam_year_choices()
    if year and all(y != year for y, _ in ch):
        ch = [(year, f'{year - 1}/{year}')] + list(ch)
    return [{'year': y, 'label': l} for y, l in ch]


def _student_base(s):
    return {'id': s.id, 'name': s.full_name, 'student_id': s.student_id or '',
            'gender': s.gender or '', 'stream': s.stream or ''}


# ---- JAMB ------------------------------------------------------------------
def jamb_payload(students, year, preselect=None):
    ids = [s.id for s in students]
    have = {r.student_id: r for r in JAMBResult.query.filter(
        JAMBResult.student_id.in_(ids), JAMBResult.exam_year == year).all()} if ids else {}
    rows = []
    for s in students:
        r = have.get(s.id)
        saved = [x for x in (s.jamb_subject_list or []) if x]
        subs = []
        for n in range(1, JAMB_SUBJECTS + 1):
            name = getattr(r, f'subject{n}') if r else None
            if not name:
                name = saved[n - 1] if len(saved) >= n else ('English Language' if n == 1 else '')
            score = getattr(r, f'subject{n}_score') if r else None
            subs.append({'name': name or '', 'value': '' if score is None else str(score)})
        rows.append({**_student_base(s), 'entered': bool(r), 'subjects': subs,
                     'total': '' if not r else str(r.total_score),
                     'has_profile_subjects': bool(saved)})
    return {'exam': 'jamb', 'board': 'JAMB', 'year': year, 'sessions': _sessions(year),
            'students': rows, 'subjects': list(WAEC_SUBJECTS), 'compulsory': 'English Language',
            'max_subject': 100, 'max_total': 400, 'preselect': preselect or '',
            'save_url': url_for('results.add_jamb'), 'list_url': url_for('results.jamb_list', year=year),
            'self_url': url_for('results.add_jamb')}


def jamb_bulk_save(year, students):
    allowed = {s.id for s in students}
    added = updated = 0
    problems = []
    for raw in request.form.getlist('sids'):
        try:
            sid = int(raw)
        except ValueError:
            continue
        st = _student_in_scope(sid) if sid in allowed else None
        if not st:
            problems.append(f'#{sid}: not allowed')
            continue
        names = [(request.form.get(f'subject{n}_{sid}') or '').strip() or None for n in range(1, 5)]
        vals = [request.form.get(f'subject{n}_score_{sid}') for n in range(1, 5)]
        scores = []
        bad = False
        for nm, v in zip(names, vals):
            if v in (None, ''):
                scores.append(None)
                continue
            try:
                iv = int(v)
            except ValueError:
                bad = True
                break
            if not 0 <= iv <= 100 or not nm:
                bad = True
                break
            scores.append(iv)
        typed = [x for x in scores if x is not None]
        total_raw = request.form.get(f'total_{sid}')
        if not bad and typed:
            total = sum(typed)
        else:
            try:
                total = int(total_raw) if total_raw not in (None, '') else None
            except ValueError:
                total = None
        if bad or total is None or not 0 <= total <= 400:
            problems.append(st.full_name)
            continue
        r = JAMBResult.query.filter_by(student_id=sid, exam_year=year).first()
        if r is None:
            r = JAMBResult(student_id=sid, exam_year=year, total_score=total)
            db.session.add(r)
            added += 1
        else:
            updated += 1
        r.total_score = total
        if typed:                                   # a breakdown was given — store it
            for n in range(1, 5):
                setattr(r, f'subject{n}', names[n - 1])
                setattr(r, f'subject{n}_score', scores[n - 1])
    db.session.commit()
    for raw in request.form.getlist('sids'):
        if raw.isdigit() and int(raw) in allowed:
            recompute_student_safe(int(raw))
    log_action('results.jamb_entry', detail=f'{year}: {added} added, {updated} updated')
    return _json_result(added, updated, problems, 'JAMB')


# ---- WAEC / NECO -------------------------------------------------------------
def waec_payload(students, year, preselect=None):
    from utils.exam_subject_config import get_config, stream_waec_map, sitting, offered
    Model = _board.model()
    board = _board.current()
    ids = [s.id for s in students]
    have = {}
    if ids:
        for r in Model.query.filter(Model.student_id.in_(ids), Model.exam_year == year).all():
            have.setdefault(r.student_id, {})[r.subject] = r.grade
    catalog = get_config()['waec']['catalog'] or list(WAEC_SUBJECTS)
    offer = offered('waec', year) or catalog
    general = sitting('waec', year)['general'] or list(WAEC_DEFAULT_SUBJECTS)
    streams = stream_waec_map(year)
    rows = []
    for s in students:
        got = have.get(s.id, {})
        saved = [x for x in (s.waec_subject_list or []) if x]
        plan = saved or streams.get(s.stream or '', []) or general
        order = [x for x in catalog if x in got] + [x for x in got if x not in catalog]
        for x in plan:
            if x not in order:
                order.append(x)
        n = max(WAEC_SLOTS, len(got))
        order = (order + [''] * n)[:n]
        rows.append({**_student_base(s), 'entered': bool(got),
                     'subjects': [{'name': x, 'value': got.get(x, '')} for x in order],
                     'has_profile_subjects': bool(saved)})
    return {'exam': board.key, 'board': board.name, 'year': year, 'sessions': _sessions(year),
            'students': rows, 'subjects': [x for x in offer] + [x for x in catalog if x not in offer],
            'offered': offer, 'grades': list(WAEC_GRADES), 'slots': WAEC_SLOTS, 'preselect': preselect or '',
            'save_url': _board.url_for('results.add_waec'),
            'list_url': _board.url_for('results.waec_list', year=year),
            'self_url': _board.url_for('results.add_waec')}


def waec_bulk_save(year, students):
    Model = _board.model()
    board = _board.current()
    allowed = {s.id for s in students}
    added = updated = 0
    problems = []
    touched = []
    for raw in request.form.getlist('sids'):
        try:
            sid = int(raw)
        except ValueError:
            continue
        st = _student_in_scope(sid) if sid in allowed else None
        if not st:
            problems.append(f'#{sid}: not allowed')
            continue
        subs = [(x or '').strip() for x in request.form.getlist(f'subj_{sid}')]
        grades = [(x or '').strip().upper() for x in request.form.getlist(f'grade_{sid}')]
        pairs = [(sb, g) for sb, g in zip(subs, grades) if sb and g]
        names = [sb for sb, _ in pairs]
        if (any(g not in WAEC_GRADES for _, g in pairs) or len(set(names)) != len(names)
                or any(g and not sb for sb, g in zip(subs, grades))):
            problems.append(st.full_name)
            continue
        existing = {r.subject: r for r in Model.query.filter_by(student_id=sid, exam_year=year).all()}
        was_entered = bool(existing)
        for sb, g in pairs:
            r = existing.pop(sb, None)
            if r:
                r.grade = g
            else:
                db.session.add(Model(student_id=sid, exam_year=year, subject=sb, grade=g))
        for r in existing.values():                  # cleared or swapped-out subjects
            db.session.delete(r)
        if pairs or was_entered:
            touched.append(sid)
            if was_entered:
                updated += 1
            else:
                added += 1
    db.session.commit()
    for sid in touched:
        recompute_student_safe(sid)
    log_action(f'results.{board.key}_entry', detail=f'{year}: {added} added, {updated} updated')
    return _json_result(added, updated, problems, board.name)


def _json_result(added, updated, problems, name):
    n = added + updated
    msg = f'Saved {name} results for {n} student{"s" if n != 1 else ""}.' if n else 'Nothing to save.'
    if problems:
        msg += ' Not saved — check their boxes: ' + ', '.join(problems[:5]) + ('…' if len(problems) > 5 else '') + '.'
    return jsonify({'ok': True, 'message': msg, 'added': added, 'updated': updated, 'problems': problems})
