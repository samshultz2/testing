"""WAEC / NECO exam timetable designer (Tools).

Build the school's copy of the SSCE timetable — papers with date and time,
hall and invigilators — see how many candidates sit each paper, catch clashes
and subjects with no paper yet, then print it (notice-board PDF, a personal
timetable per candidate, or Excel)."""
import datetime as dt
import re

from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, abort, session

from models import db, ExamTimetable, ExamTimetablePaper
from utils.access_control import login_required, can_use_tool
from utils.branch_scope import scope_query, require_branch_access, branch_for_new
from utils.helpers import WAEC_SUBJECTS
from utils import exam_timetable as ET

exam_timetable_bp = Blueprint('exam_timetable', __name__, url_prefix='/tools/exam-timetable')

# How each body names its papers on the official SSCE timetable, with the
# paper type each implies. WAEC numbers 1-2-3 (1 Objective, 2 Essay,
# 3 Practical / Alternative to Practical Work; English 3 is the Test of
# Orals); NECO uses Roman numerals the other way round (I Practical,
# II Essay, III Objective) and usually sits III & II together.
PAPER_PRESETS = {
    'waec': [('Paper 1 (Objective)', 'objective'), ('Paper 2 (Essay)', 'essay'),
             ('Papers 2 & 1 (Essay & Objective)', 'combined'), ('Paper 3 (Practical)', 'practical'),
             ('Paper 3 (Alternative to Practical Work)', 'alt_practical'), ('Paper 3 (Test of Orals)', 'oral'),
             ('Paper 3 (Listening Comprehension)', 'oral'), ('Paper 3 (Drawing)', 'drawing'),
             ('Paper 4 (Project / Coursework)', 'project')],
    'neco': [('Paper I: Practical', 'practical'), ('Paper II: Essay', 'essay'), ('Paper III: Objective', 'objective'),
             ('Papers III & II: Objective & Essay', 'combined'), ('Papers III & I: Objective & Practical', 'objective_practical'),
             ('Paper I: Alternative to Practical', 'alt_practical'), ('Paper IV: Test of Orals', 'oral'),
             ('Paper I: Drawing', 'drawing'), ('Paper IV: Project / Coursework', 'project')],
}

# Subjects whose papers are named differently from the usual Objective /
# Essay / Practical — offered first when that subject is chosen. Literature:
# WAEC 1 Objective, 2 Prose, 3 Drama & Poetry (Prose and Objective sat back
# to back); NECO II Drama & Poetry, III Objective, IV Prose (III & IV
# usually sat together). English: WAEC Paper 3 / NECO Paper IV is the Test
# of Orals (45 mins). Geography: WAEC 3 is 'Practical and Physical
# Geography'; NECO I Practical / Physical, II Essay (Human & Regional),
# III Objective, with III & I usually sat together.
SUBJECT_PAPERS = {
    'waec': {
        'literature in english': [
            ('Paper 1 (Objective)', 'objective'), ('Paper 2 (Prose)', 'prose'),
            ('Papers 2 & 1 (Prose & Objective)', 'objective_prose'), ('Paper 3 (Drama & Poetry)', 'drama_poetry')],
        'english language': [
            ('Paper 1 (Objective)', 'objective'), ('Paper 2 (Essay)', 'essay'),
            ('Papers 2 & 1 (Essay & Objective)', 'combined'), ('Paper 3 (Test of Orals)', 'oral')],
        'visual arts': [
            ('Paper 1 (Objective)', 'objective'), ('Paper 2 (Essay)', 'essay'),
            ('Paper 3A (Drawing)', 'drawing'), ('Paper 3B (Craft / Design)', 'practical')],
        'technical drawing': [
            ('Paper 1 (Objective)', 'objective'), ('Paper 2 (Essay)', 'essay'), ('Paper 3 (Drawing)', 'drawing')],
        'geography': [
            ('Paper 1 (Objective)', 'objective'), ('Paper 2 (Essay)', 'essay'),
            ('Papers 2 & 1 (Essay & Objective)', 'combined'),
            ('Paper 3 (Practical and Physical Geography)', 'practical_physical')],
    },
    # NECO wording below follows the official 2027 SSCE Internal timetable.
    'neco': {
        'literature in english': [
            ('Paper II: Drama & Poetry', 'drama_poetry'), ('Papers III & IV: Objective & Prose', 'objective_prose'),
            ('Paper III: Objective', 'objective'), ('Paper IV: Prose', 'prose')],
        'english language': [
            ('Paper III: Objective', 'objective'), ('Paper II: Essay', 'essay'),
            ('Paper IV: Test of Orals', 'oral'), ('Papers III & II: Objective & Essay', 'combined')],
        'mathematics': [
            ('Paper III: Objective', 'objective'), ('Paper II: Essay', 'essay'),
            ('Papers III & II: Objective & Essay', 'combined')],
        'further mathematics': [
            ('Paper III: Objective', 'objective'), ('Paper II: Essay', 'essay'),
            ('Papers III & II: Objective & Essay', 'combined')],
        'geography': [
            ('Papers III & I: Objective & Practical & Physical', 'objective_practical'),
            ('Paper II: Essay - Human and Regional Geography', 'essay'),
            ('Paper III: Objective', 'objective'), ('Paper I: Practical & Physical', 'practical_physical')],
        'technical drawing': [
            ('Paper I: Practical', 'practical'), ('Papers III & IV: Objective & Drawing', 'drawing')],
        'visual arts': [
            ('Papers III & II: Objective & Essay', 'combined'), ('Paper I: Drawing', 'drawing'),
            ('Paper IV: Creative Design', 'project')],
        'financial accounting': [
            ('Papers III & II: Objective, Theory & Practice', 'combined')],
        'french': [
            ('Paper I: Written Comprehension', 'essay'), ('Paper II: Written Expression', 'essay'),
            ('Paper IV: Oral French', 'oral')],
        'arabic': [
            ('Papers III & II: Objective, Essay & Literature', 'combined'), ('Paper IV: Oral Arabic', 'oral')],
        'music': [
            ('Paper I: Performance Test, Music Technology & Alternative To Music Technology', 'practical'),
            ('Papers III & II: Objective & Essay', 'combined'), ('Paper IV: Aural Music', 'oral')],
        'health education': [
            ('Paper I: Test of Practical', 'practical'), ('Papers III & II: Objective & Essay', 'combined')],
        'physical education': [
            ('Paper I: Practical', 'practical'), ('Papers III & II: Objective & Essay', 'combined')],
    },
}
SUBJECT_ALIASES = {'literature-in-english': 'literature in english', 'literature': 'literature in english',
                   'general mathematics': 'mathematics', 'accounting': 'financial accounting',
                   'visual art': 'visual arts',
                   'english': 'english language', 'visual art': 'visual arts', 'fine art': 'visual arts',
                   'fine arts': 'visual arts'}


def papers_for(board, subject):
    """The paper choices for a subject: its own names first, then the
    body's usual papers (without repeats)."""
    key = ET.norm(subject).replace('-', ' ')
    key = SUBJECT_ALIASES.get(ET.norm(subject), SUBJECT_ALIASES.get(key, key))
    own = SUBJECT_PAPERS.get(board, {}).get(key, [])
    seen = {lbl for lbl, _k in own}
    return own + [(lbl, k) for lbl, k in PAPER_PRESETS.get(board, PAPER_PRESETS['waec']) if lbl not in seen]


@exam_timetable_bp.before_request
def _gate():
    if session.get('logged_in') and not can_use_tool('exam_timetable'):
        abort(403)


def _tt_or_404(tt_id):
    tt = db.get_or_404(ExamTimetable, tt_id)
    require_branch_access(tt.branch_id)
    return tt


def _parse_date(v):
    try:
        return dt.date.fromisoformat((v or '').strip())
    except ValueError:
        return None


def _parse_time(v):
    m = re.match(r'^\s*(\d{1,2}):(\d{2})', v or '')
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return dt.time(h, mi) if 0 <= h < 24 and 0 <= mi < 60 else None


def _paper_from_form(form, paper=None, tt=None):
    """Fill/validate a paper from the form; returns (paper, error)."""
    d, s, e = _parse_date(form.get('exam_date')), _parse_time(form.get('start_time')), _parse_time(form.get('end_time'))
    subject = form.get('subject') or ''
    if subject == '__other':
        subject = form.get('subject_other') or ''
    subject = subject.strip()[:120]
    if not (d and s and e and subject):
        return None, 'Give the paper a date, start and end time, and subject.'
    if e <= s:
        return None, 'The paper must end after it starts.'
    if tt is not None and tt.start_date and d < tt.start_date:
        return None, 'That date is before the exam starts (%s).' % tt.start_date.strftime('%d %b %Y')
    if tt is not None and tt.end_date and d > tt.end_date:
        return None, 'That date is after the exam ends (%s).' % tt.end_date.strftime('%d %b %Y')
    paper = paper or ExamTimetablePaper()
    paper.exam_date, paper.start_time, paper.end_time, paper.subject = d, s, e, subject
    pp = form.get('paper') or ''
    if pp == '__other':
        pp = form.get('paper_other') or ''
    paper.paper = pp.strip()[:120] or None
    kind = form.get('kind') or ''
    paper.kind = kind if kind in ET.KIND_LABEL else None
    paper.venue = (form.get('venue') or '').strip()[:120] or None
    paper.invigilators = (form.get('invigilators') or '').strip()[:255] or None
    paper.notes = (form.get('notes') or '').strip()[:255] or None
    return paper, None


def _short(t):
    return ('%d:%02d%s' % (t.hour % 12 or 12, t.minute, 'am' if t.hour < 12 else 'pm')).replace(':00', '')


def _sessions(board):
    out = []
    for a, b in ET.COMMON_SESSIONS.get(board, ET.COMMON_SESSIONS['waec']):
        s, e = _parse_time(a), _parse_time(b)
        m = ET.minutes(s, e)
        out.append({'start': a, 'end': b, 'minutes': m, 'dur': ET.fmt_dur(m),
                    'label': '%s–%s' % (_short(s), _short(e))})
    return out


@exam_timetable_bp.route('/')
@login_required
def index():
    tts = scope_query(ExamTimetable.query, ExamTimetable).order_by(ExamTimetable.created_at.desc()).all()
    rows = []
    for t in tts:
        dates = [p.exam_date for p in t.papers]
        rows.append({'t': t, 'papers': len(t.papers), 'first': min(dates) if dates else None,
                     'last': max(dates) if dates else None})
    return render_template('exam_timetable/index.html', rows=rows, this_year=dt.date.today().year)


def _window(form):
    """(start, end, error) from the form's exam start/end dates (both optional)."""
    a, b = _parse_date(form.get('start_date')), _parse_date(form.get('end_date'))
    if a and b and b < a:
        return None, None, 'The exam must end on or after the day it starts.'
    return a, b, None


@exam_timetable_bp.route('/create', methods=['POST'])
@login_required
def create():
    board = 'neco' if request.form.get('board') == 'neco' else 'waec'
    start, end, err = _window(request.form)
    if err:
        flash(err, 'error')
        return redirect(url_for('exam_timetable.index'))
    year = request.form.get('year', type=int) or (start.year if start else dt.date.today().year)
    title = (request.form.get('title') or '').strip()[:150] or \
        '%s SSCE %d timetable' % ('NECO' if board == 'neco' else 'WAEC', year)
    tt = ExamTimetable(branch_id=branch_for_new(), board=board, year=year, title=title,
                       start_date=start, end_date=end, created_by=session.get('username') or 'Admin')
    src = request.form.get('copy_from', type=int)
    if src:
        _copy_papers(_tt_or_404(src), tt)
    db.session.add(tt)
    db.session.commit()
    from utils.audit import log_action
    log_action('exam_timetable.create', title)
    return redirect(url_for('exam_timetable.edit', tt_id=tt.id))


def _copy_papers(old, new):
    """Copy every paper; when both have a start date, shift the dates so the
    first exam day lines up with the new window."""
    shift = dt.timedelta(0)
    first = min((p.exam_date for p in old.papers), default=None)
    if new.start_date and first:
        shift = new.start_date - (old.start_date or first)
    for p in old.papers:
        new.papers.append(ExamTimetablePaper(
            exam_date=p.exam_date + shift, start_time=p.start_time, end_time=p.end_time, subject=p.subject,
            paper=p.paper, kind=p.kind, venue=p.venue, invigilators=p.invigilators, notes=p.notes))


@exam_timetable_bp.route('/<int:tt_id>/duplicate', methods=['POST'])
@login_required
def duplicate(tt_id):
    old = _tt_or_404(tt_id)
    tt = ExamTimetable(branch_id=old.branch_id, board=old.board, year=old.year, title=(old.title + ' (copy)')[:150],
                       start_date=old.start_date, end_date=old.end_date, notes=old.notes,
                       created_by=session.get('username') or 'Admin')
    _copy_papers(old, tt)
    db.session.add(tt)
    db.session.commit()
    flash('Copied “%s”.' % old.title, 'success')
    return redirect(url_for('exam_timetable.edit', tt_id=tt.id))


@exam_timetable_bp.route('/<int:tt_id>')
@login_required
def edit(tt_id):
    tt = _tt_or_404(tt_id)
    cands = ET.candidates(tt.board)
    data = ET.analyse(tt, cands)
    mine = sorted({n for c in cands for n in c['subject_names']}, key=str.lower)
    # Only subjects this body sets (NECO: Digital Technologies → Computer Studies).
    rest = sorted({ET.board_subject(tt.board, x) for x in WAEC_SUBJECTS} - set(mine), key=str.lower)
    subjects = mine + rest
    last = data['rows'][-1]['p'] if data['rows'] else None
    return render_template('exam_timetable/edit.html', xt=tt, d=data, subjects=subjects, subj_mine=mine, subj_rest=rest, presets=PAPER_PRESETS.get(tt.board, PAPER_PRESETS['waec']),
                           papers_for=lambda subj: papers_for(tt.board, subj),
                           paper_sets={k: v for k, v in SUBJECT_PAPERS.get(tt.board, {}).items()},
                           subject_aliases=SUBJECT_ALIASES,
                           kinds=ET.KINDS, fmt_time=ET.fmt_time, fmt_dur=ET.fmt_dur, last=last,
                           sessions=_sessions(tt.board), durations=ET.DURATIONS,
                           **_export_ctx(tt),
                           others=[t for t in scope_query(ExamTimetable.query, ExamTimetable).all() if t.id != tt.id])


@exam_timetable_bp.route('/<int:tt_id>/details', methods=['POST'])
@login_required
def save_details(tt_id):
    tt = _tt_or_404(tt_id)
    start, end, err = _window(request.form)
    if err:
        flash(err, 'error')
        return redirect(url_for('exam_timetable.edit', tt_id=tt.id) + '#details')
    tt.title = (request.form.get('title') or '').strip()[:150] or tt.title
    if request.form.get('board') in ('waec', 'neco'):
        tt.board = request.form['board']
    tt.year = request.form.get('year', type=int) or tt.year
    tt.start_date, tt.end_date = start, end
    tt.notes = (request.form.get('notes') or '').strip() or None
    db.session.commit()
    outside = [p for p in tt.papers if (start and p.exam_date < start) or (end and p.exam_date > end)]
    if outside:
        flash('Saved. %d paper%s fall outside the new exam dates — move or remove %s.' % (
            len(outside), '' if len(outside) == 1 else 's', 'it' if len(outside) == 1 else 'them'), 'warning')
    else:
        flash('Saved.', 'success')
    return redirect(url_for('exam_timetable.edit', tt_id=tt.id))


@exam_timetable_bp.route('/<int:tt_id>/papers', methods=['POST'])
@login_required
def add_paper(tt_id):
    tt = _tt_or_404(tt_id)
    paper, err = _paper_from_form(request.form, tt=tt)
    if err:
        flash(err, 'error')
        return redirect(url_for('exam_timetable.edit', tt_id=tt.id))
    tt.papers.append(paper)
    db.session.commit()
    flash('Added %s%s.' % (paper.subject, (' — ' + paper.paper) if paper.paper else ''), 'success')
    # Keep date, times, hall, invigilators and subject for the next paper —
    # usually the same subject's next paper or another subject in the same session.
    return redirect(url_for('exam_timetable.edit', tt_id=tt.id, after=paper.exam_date.isoformat(),
                            s=paper.start_time.strftime('%H:%M'), e=paper.end_time.strftime('%H:%M'),
                            v=paper.venue or '', inv=paper.invigilators or '', subj=paper.subject) + '#add')


def _prompt(tt, subjects):
    body = tt.board_label
    wanted = ', '.join(subjects) if subjects else 'every subject'
    papers = '; '.join(lbl for lbl, _k in PAPER_PRESETS.get(tt.board, PAPER_PRESETS['waec'])[:4])
    return (
        "Read this {body} SSCE timetable{yr} (photo, screenshot or PDF). Output one line per paper, "
        "as comma-separated values in EXACTLY this order:\n\n"
        "date, start, end, subject, paper\n\n"
        "- date as YYYY-MM-DD.\n"
        "- start and end as times like 9:30am and 12:30pm (if only a duration is shown, put the duration, e.g. 1hr 30mins, as end).\n"
        "- subject exactly as the subject is named (e.g. English Language, Literature in English).\n"
        "- paper as printed on the timetable, e.g. {papers}.\n"
        "- If the timetable prints papers together as ONE sitting with one time (e.g. 'Papers III & I: Objective & Practical & Physical'), keep them as ONE line, paper exactly as printed.\n"
        "- If papers have their own times (e.g. Essay 9:30am-11:30am then Objective 11:30am-12:30pm), give each its own line.\n"
        "- Skip papers marked 'to be determined' or with no date/time.\n"
        "- Only include these subjects: {wanted}.\n"
        "- Output only the rows. No headings, no totals, no extra text, no code block.\n\n"
        "Example:\n"
        "{ex}"
    ).format(body=body, yr=(' %s' % tt.year) if tt.year else '', papers=papers, wanted=wanted,
             ex=("2026-06-05, 9:30am, 11:30am, Geography, Paper 2 (Essay)\n"
                 "2026-06-05, 11:30am, 12:30pm, Geography, Paper 1 (Objective)") if tt.board == 'waec' else
                ("2027-04-28, 2:00pm, 4:30pm, Geography, Papers III & I: Objective & Practical & Physical\n"
                 "2027-05-07, 10:00am, 12:00pm, Geography, Paper II: Essay - Human and Regional Geography"))


@exam_timetable_bp.route('/<int:tt_id>/paste', methods=['GET', 'POST'])
@login_required
def paste(tt_id):
    """Add many papers at once: paste rows (from a chatbot reading the
    official timetable, a spreadsheet, or typed), preview, then save."""
    tt = _tt_or_404(tt_id)
    cands = ET.candidates(tt.board)
    mine = sorted({n for c in cands for n in c['subject_names']}, key=str.lower)
    subjects = mine + sorted({ET.board_subject(tt.board, x) for x in WAEC_SUBJECTS} - set(mine), key=str.lower)
    text = request.form.get('data', '') if request.method == 'POST' else ''
    rows, summary = [], None
    if request.method == 'POST' and text.strip():
        rows = ET.parse_paste(text, subjects, lambda subj: papers_for(tt.board, subj),
                              default_year=tt.year or (tt.start_date.year if tt.start_date else None), board=tt.board)
        have = {(p.exam_date, p.start_time, ET.norm(p.subject), ET.norm(p.paper or '')) for p in tt.papers}
        for r in rows:
            if r['error']:
                continue
            if tt.start_date and r['date'] < tt.start_date or tt.end_date and r['date'] > tt.end_date:
                r['error'] = 'Outside the exam dates'
            elif (r['date'], r['start'], ET.norm(r['subject']), ET.norm(r['paper'] or '')) in have:
                r['dup'] = True
        ok = [r for r in rows if not r['error'] and not r.get('dup')]
        summary = {'ok': len(ok), 'errors': sum(1 for r in rows if r['error']),
                   'dups': sum(1 for r in rows if r.get('dup')),
                   'unknown': sum(1 for r in ok if not r['known'])}
        if request.form.get('action') == 'save' and ok:
            for r in ok:
                tt.papers.append(ExamTimetablePaper(
                    exam_date=r['date'], start_time=r['start'], end_time=r['end'], subject=r['subject'][:120],
                    paper=(r['paper'] or '')[:120] or None, kind=r['kind'], venue=(r['venue'] or '')[:120] or None,
                    invigilators=(r['invigilators'] or '')[:255] or None))
            db.session.commit()
            from utils.audit import log_action
            log_action('exam_timetable.paste', '%s: %d papers' % (tt.title, len(ok)))
            flash('Added %d paper%s.' % (len(ok), '' if len(ok) == 1 else 's'), 'success')
            return redirect(url_for('exam_timetable.edit', tt_id=tt.id))
    return render_template('exam_timetable/paste.html', xt=tt, text=text, rows=rows, summary=summary,
                           prompt=_prompt(tt, mine), kinds=dict(ET.KINDS), fmt_time=ET.fmt_time, fmt_dur=ET.fmt_dur,
                           minutes=ET.minutes)


@exam_timetable_bp.route('/<int:tt_id>/papers/<int:paper_id>', methods=['POST'])
@login_required
def update_paper(tt_id, paper_id):
    tt = _tt_or_404(tt_id)
    paper = db.get_or_404(ExamTimetablePaper, paper_id)
    if paper.timetable_id != tt.id:
        abort(404)
    if request.form.get('delete'):
        db.session.delete(paper)
        db.session.commit()
        flash('Paper removed.', 'success')
        return redirect(url_for('exam_timetable.edit', tt_id=tt.id))
    _p, err = _paper_from_form(request.form, paper, tt=tt)
    if err:
        db.session.rollback()
        flash(err, 'error')
    else:
        db.session.commit()
        flash('Paper updated.', 'success')
    return redirect(url_for('exam_timetable.edit', tt_id=tt.id) + '#p%d' % paper.id)


@exam_timetable_bp.route('/<int:tt_id>/delete', methods=['POST'])
@login_required
def delete(tt_id):
    tt = _tt_or_404(tt_id)
    title = tt.title
    db.session.delete(tt)
    db.session.commit()
    from utils.audit import log_action
    log_action('exam_timetable.delete', title)
    flash('Deleted “%s”.' % title, 'success')
    return redirect(url_for('exam_timetable.index'))


THEMES = [('timeline', 'Timeline', 'cream & gold, dated'), ('tickets', 'Tickets', 'one cut-out ticket per day'),
          ('gazette', 'Gazette', 'school newspaper, black & white'), ('swiss', 'Swiss', 'bold poster type, one accent'),
          ('notebook', 'Exercise Book', 'ruled page, index tabs'), ('board', 'Board', 'big, light, best for phones'),
          ('quiet', 'Quiet', 'clean, calm, one accent'), ('inline', 'Inline', 'one line per paper, like a message'),
          ('print', 'Print', 'bold sans, grey header, striped'), ('mono', 'Mono', 'B&W, photocopy-friendly'),
          ('plain', 'Plain', 'pure black & white, no shading')]


def _export_ctx(tt):
    """What the export panel needs (Download modal and full print page)."""
    from utils.school import logo_url, school_profile
    return {'school': school_profile() or {}, 'logo': logo_url(), 'themes': THEMES, 'kind_map': dict(ET.KINDS),
            'export_name': re.sub(r'[^A-Za-z0-9]+', '_', tt.title).strip('_')[:60] or 'exam_timetable'}


@exam_timetable_bp.route('/<int:tt_id>/print')
@login_required
def print_view(tt_id):
    """The one-page timetable for the notice board, in the timetable
    designer's themes; downloaded as PDF / image or printed from the page."""
    tt = _tt_or_404(tt_id)
    if not tt.papers:
        flash('Add papers first.', 'warning')
        return redirect(url_for('exam_timetable.edit', tt_id=tt.id))
    data = ET.analyse(tt, ET.candidates(tt.board))
    theme = request.args.get('theme')
    return render_template('exam_timetable/print.html', xt=tt, d=data,
                           theme=theme if theme in dict((t[0], 1) for t in THEMES) else '',
                           fmt_time=ET.fmt_time, fmt_dur=ET.fmt_dur, **_export_ctx(tt))


@exam_timetable_bp.route('/<int:tt_id>/export')
@login_required
def export(tt_id):
    tt = _tt_or_404(tt_id)
    if not tt.papers:
        flash('Add papers first.', 'warning')
        return redirect(url_for('exam_timetable.edit', tt_id=tt.id))
    cands = ET.candidates(tt.board)
    data = ET.analyse(tt, cands)
    fmt = (request.args.get('format') or 'pdf').lower()
    stem = re.sub(r'[^A-Za-z0-9]+', '_', tt.title).strip('_')[:60] or 'exam_timetable'
    if fmt in ('excel', 'xlsx'):
        return Response(ET.render_xlsx(tt, cands, data),
                        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        headers={'Content-Disposition': f'attachment; filename="{stem}.xlsx"'})
    per = fmt == 'candidates'
    return Response(ET.render_pdf(tt, cands, data, per_student=per), mimetype='application/pdf',
                    headers={'Content-Disposition': f'attachment; filename="{stem}{"_candidates" if per else ""}.pdf"'})
