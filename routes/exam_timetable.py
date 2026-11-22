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

PAPER_PRESETS = ['Paper 1 (Objective)', 'Paper 2 (Essay)', 'Paper 3 (Practical)', 'Paper 1 & 2',
                 'Paper 3 (Alternative to Practical)', 'Oral / Listening']


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


def _paper_from_form(form, paper=None):
    """Fill/validate a paper from the form; returns (paper, error)."""
    d, s, e = _parse_date(form.get('exam_date')), _parse_time(form.get('start_time')), _parse_time(form.get('end_time'))
    subject = (form.get('subject') or '').strip()[:120]
    if not (d and s and e and subject):
        return None, 'Give the paper a date, start and end time, and subject.'
    if e <= s:
        return None, 'The paper must end after it starts.'
    paper = paper or ExamTimetablePaper()
    paper.exam_date, paper.start_time, paper.end_time, paper.subject = d, s, e, subject
    paper.paper = (form.get('paper') or '').strip()[:120] or None
    kind = form.get('kind') or ''
    paper.kind = kind if kind in ET.KIND_LABEL else None
    paper.venue = (form.get('venue') or '').strip()[:120] or None
    paper.invigilators = (form.get('invigilators') or '').strip()[:255] or None
    paper.notes = (form.get('notes') or '').strip()[:255] or None
    return paper, None


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


@exam_timetable_bp.route('/create', methods=['POST'])
@login_required
def create():
    board = 'neco' if request.form.get('board') == 'neco' else 'waec'
    year = request.form.get('year', type=int) or dt.date.today().year
    title = (request.form.get('title') or '').strip()[:150] or \
        '%s SSCE %d timetable' % ('NECO' if board == 'neco' else 'WAEC', year)
    tt = ExamTimetable(branch_id=branch_for_new(), board=board, year=year, title=title,
                       created_by=session.get('username') or 'Admin')
    src = request.form.get('copy_from', type=int)
    if src:
        old = _tt_or_404(src)
        shift = dt.timedelta(days=0)
        for p in old.papers:
            tt.papers.append(ExamTimetablePaper(
                exam_date=p.exam_date + shift, start_time=p.start_time, end_time=p.end_time, subject=p.subject,
                paper=p.paper, kind=p.kind, venue=p.venue, invigilators=p.invigilators, notes=p.notes))
    db.session.add(tt)
    db.session.commit()
    from utils.audit import log_action
    log_action('exam_timetable.create', title)
    return redirect(url_for('exam_timetable.edit', tt_id=tt.id))


@exam_timetable_bp.route('/<int:tt_id>')
@login_required
def edit(tt_id):
    tt = _tt_or_404(tt_id)
    cands = ET.candidates(tt.board)
    data = ET.analyse(tt, cands)
    subjects = sorted({n for c in cands for n in c['subject_names']} | set(WAEC_SUBJECTS), key=str.lower)
    last = data['rows'][-1]['p'] if data['rows'] else None
    return render_template('exam_timetable/edit.html', xt=tt, d=data, subjects=subjects, presets=PAPER_PRESETS,
                           kinds=ET.KINDS, fmt_time=ET.fmt_time, fmt_dur=ET.fmt_dur, last=last,
                           others=[t for t in scope_query(ExamTimetable.query, ExamTimetable).all() if t.id != tt.id])


@exam_timetable_bp.route('/<int:tt_id>/details', methods=['POST'])
@login_required
def save_details(tt_id):
    tt = _tt_or_404(tt_id)
    tt.title = (request.form.get('title') or '').strip()[:150] or tt.title
    tt.year = request.form.get('year', type=int) or tt.year
    tt.notes = (request.form.get('notes') or '').strip() or None
    db.session.commit()
    flash('Saved.', 'success')
    return redirect(url_for('exam_timetable.edit', tt_id=tt.id))


@exam_timetable_bp.route('/<int:tt_id>/papers', methods=['POST'])
@login_required
def add_paper(tt_id):
    tt = _tt_or_404(tt_id)
    paper, err = _paper_from_form(request.form)
    if err:
        flash(err, 'error')
        return redirect(url_for('exam_timetable.edit', tt_id=tt.id))
    tt.papers.append(paper)
    db.session.commit()
    flash('Added %s%s.' % (paper.subject, (' — ' + paper.paper) if paper.paper else ''), 'success')
    return redirect(url_for('exam_timetable.edit', tt_id=tt.id, after=paper.exam_date.isoformat()) + '#add')


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
    _p, err = _paper_from_form(request.form, paper)
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


@exam_timetable_bp.route('/<int:tt_id>/print')
@login_required
def print_view(tt_id):
    """The one-page timetable for the notice board, in the timetable
    designer's themes; downloaded as PDF / image or printed from the page."""
    from utils.school import logo_url, school_profile
    tt = _tt_or_404(tt_id)
    if not tt.papers:
        flash('Add papers first.', 'warning')
        return redirect(url_for('exam_timetable.edit', tt_id=tt.id))
    cands = ET.candidates(tt.board)
    data = ET.analyse(tt, cands)
    theme = request.args.get('theme')
    return render_template('exam_timetable/print.html', xt=tt, d=data, themes=THEMES,
                           theme=theme if theme in dict((t[0], 1) for t in THEMES) else '',
                           school=school_profile() or {}, logo=logo_url(), kinds=dict(ET.KINDS),
                           fmt_time=ET.fmt_time, fmt_dur=ET.fmt_dur)


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
