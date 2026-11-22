"""Exam Hall Allocator (Tools).

Admin tool that spreads exam candidates across halls to curb malpractice:
students from the same class + arm are scattered across as many halls as
possible, halls fill in proportion to capacity (a big Main hall holds more),
and each hall is gender-balanced where possible.
"""
import json

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, session, Response, abort)
from models import db, Student, StudentEnrollment, ClassArmAssignment, ExamHallPlan
from utils.helpers import get_active_term
from utils.branch_scope import (scope_query, viewing_branch_id, can_access_branch,
                                 require_branch_access, branch_for_new)
from utils.access_control import login_required, is_admin
from utils.exam_hall_allocator import allocate_halls, seat_hall

# Candidate sets the tool can seat, so it fits internal exams, WAEC and JAMB.
CANDIDATE_SETS = {
    'all': 'All enrolled students',
    'waec': 'WAEC-registered only (has WAEC reg. number)',
    'jamb': 'JAMB-registered only (has JAMB reg. number)',
}
STREAMS = ['Science', 'Arts', 'Commercial']

exam_halls_bp = Blueprint('exam_halls', __name__, url_prefix='/tools/exam-halls')


def _admin_only():
    if not is_admin():
        abort(403)


def _assignments_for_term():
    """Branch-scoped class-arm assignments for the active term, each with its
    active-student count (only those with students are worth showing)."""
    term = get_active_term()
    if not term:
        return []
    q = scope_query(ClassArmAssignment.query.filter_by(term_id=term.id), ClassArmAssignment)
    assignments = q.all()
    from sqlalchemy import func
    counts = dict(db.session.query(
            StudentEnrollment.class_arm_assignment_id, func.count(StudentEnrollment.id))
        .filter(StudentEnrollment.class_arm_assignment_id.in_([a.id for a in assignments]),
                StudentEnrollment.is_active == True)
        .group_by(StudentEnrollment.class_arm_assignment_id).all()) if assignments else {}
    rows = []
    for a in assignments:
        count = counts.get(a.id, 0)
        if count:
            rows.append({'id': a.id, 'label': a.display_name,
                         'class_name': a.school_class.name if a.school_class else '',
                         'arm': a.arm_label, 'count': count})
    rows.sort(key=lambda r: (r['class_name'], r['arm']))
    return rows


def _masthead():
    from utils.school import school_profile
    from models.models_branch import Branch
    sname = (school_profile() or {}).get('name') or ''
    bid = viewing_branch_id()
    if bid and bid not in (None, -1):
        b = db.session.get(Branch, bid)
        branch = b.name if b else ''
    else:
        branches = Branch.query.all()
        branch = branches[0].name if len(branches) == 1 else 'All Branches'
    term = get_active_term()
    return sname, branch, (term.full_name if term else '')


def _parse_halls(form):
    """Read the parallel hall_name[]/hall_capacity[] fields + the main-hall pick."""
    names = form.getlist('hall_name')
    caps = form.getlist('hall_capacity')
    main_idx = form.get('main_hall', type=int)
    halls = []
    for i, (nm, cap) in enumerate(zip(names, caps)):
        nm = (nm or '').strip()
        try:
            cap = int(cap)
        except (TypeError, ValueError):
            cap = 0
        if not nm and cap <= 0:
            continue
        halls.append({'name': nm or f'Hall {i + 1}', 'capacity': cap,
                      'is_main': (main_idx == i)})
    return halls


def _gather_groups(form):
    """Selected class-arm assignments -> allocator groups (branch/access checked),
    narrowed by candidate set (all / WAEC / JAMB registered) and stream."""
    from utils.access_control import can_access_class
    ids = form.getlist('assignments', type=int)
    cand = form.get('candidate_set', 'all')
    streams = set(form.getlist('streams'))

    def keep(s):
        if cand == 'waec' and not (s.waec_reg_number or '').strip():
            return False
        if cand == 'jamb' and not (s.jamb_reg_number or '').strip():
            return False
        if streams and (s.stream or '') not in streams:
            return False
        return True

    groups = []
    for aid in ids:
        a = db.session.get(ClassArmAssignment, aid)
        if not a or not can_access_class(aid):
            continue
        enrs = (StudentEnrollment.query.filter_by(class_arm_assignment_id=aid, is_active=True)
                .join(Student).filter(Student.is_active == True).order_by(Student.surname, Student.first_name).all())
        studs = []
        for e in enrs:
            s = e.student
            if not s or not keep(s):
                continue
            studs.append({'id': s.id, 'student_id': s.student_id, 'name': s.full_name,
                          'gender': s.gender, 'class_name': a.school_class.name if a.school_class else '',
                          'class_level': (a.school_class.level or 0) if a.school_class else 0,
                          'arm': a.arm_label})
        if studs:
            groups.append({'key': a.display_name, 'students': studs})
    return groups


PAYLOAD_KEYS = ('assignments', 'hall_name', 'hall_capacity', 'main_hall', 'balance_gender',
                'diversify_classes', 'candidate_set', 'streams', 'seats_per_row', 'seed')


def _payload(form, seed):
    return {'assignments': form.getlist('assignments'),
            'hall_name': form.getlist('hall_name'),
            'hall_capacity': form.getlist('hall_capacity'),
            'main_hall': form.get('main_hall', ''),
            'balance_gender': 'on' if form.get('balance_gender') == 'on' else '',
            'diversify_classes': 'on' if form.get('diversify_classes') == 'on' else '',
            'candidate_set': form.get('candidate_set', 'all'),
            'streams': form.getlist('streams'),
            'seats_per_row': str(form.get('seats_per_row', type=int) or 5),
            'seed': str(seed)}


def _run(form, fresh=False):
    """Allocate from the submitted form. Returns (result, payload); raises
    ValueError with a message for the user. ``fresh`` draws a new seed."""
    import random as _random
    groups = _gather_groups(form)
    halls = _parse_halls(form)
    if not groups:
        raise ValueError('Select at least one class/arm that has students.')
    if not halls:
        raise ValueError('Add at least one hall with a capacity.')
    seed = None if fresh else form.get('seed', type=int)
    if seed is None:
        seed = _random.randrange(1_000_000_000)
    cols = form.get('seats_per_row', type=int) or 5
    result = allocate_halls(groups, halls, balance_gender=form.get('balance_gender') == 'on', seed=seed,
                            diversify_classes=form.get('diversify_classes') == 'on')
    for i, hall in enumerate(result['halls']):
        hall['seating'] = seat_hall(hall['students'], cols=cols, seed=seed + i)
    _add_class_breakdown(result, groups)
    return result, _payload(form, seed)


def _add_class_breakdown(result, groups):
    """Per hall: how many of each class (SSS1, SSS2 …) sit there; plus the
    class list in school order for the table columns."""
    level = {}
    for g in groups:
        for s in g['students']:
            level.setdefault(s.get('class_name') or '', s.get('class_level') or 0)
    result['classes'] = sorted(level, key=lambda c: (level[c], c))
    for hall in result['halls']:
        bc = {}
        for s in hall['students']:
            c = s.get('class_name') or ''
            bc[c] = bc.get(c, 0) + 1
        hall['by_class'] = {c: bc[c] for c in result['classes'] if c in bc}


def _snapshot(result):
    """The JSON-safe arrangement to store on a saved plan."""
    keep = ('id', 'student_id', 'name', 'gender', 'class_name', 'arm')
    halls = []
    for h in result['halls']:
        seating = h.get('seating') or {}
        rows = [[({'seat': c['seat'], 'student': {k: c['student'].get(k) for k in keep}} if c else None)
                 for c in row] for row in seating.get('rows') or []]
        halls.append({'name': h['name'], 'capacity': h['capacity'], 'is_main': h['is_main'],
                      'count': h['count'], 'gender': h['gender'], 'by_group': h['by_group'],
                      'by_class': h.get('by_class') or {},
                      'students': [{k: s.get(k) for k in keep} for s in h['students']],
                      'seating': {'rows': rows, 'cols': seating.get('cols'), 'nrows': seating.get('nrows'),
                                  'conflicts': seating.get('conflicts', 0)}})
    return {'halls': halls, 'groups': result['groups'], 'classes': result.get('classes') or [],
            'total_students': result['total_students'], 'total_capacity': result['total_capacity'],
            'balanced_by_gender': result.get('balanced_by_gender')}


def _plans():
    return (scope_query(ExamHallPlan.query, ExamHallPlan)
            .order_by(ExamHallPlan.created_at.desc()).limit(60).all())


def _plan_or_404(plan_id):
    plan = db.get_or_404(ExamHallPlan, plan_id)
    require_branch_access(plan.branch_id)
    return plan


@exam_halls_bp.route('/')
@login_required
def index():
    _admin_only()
    return render_template('exam_halls/index.html',
                           assignments=_assignments_for_term(),
                           candidate_sets=CANDIDATE_SETS, streams=STREAMS,
                           has_term=bool(get_active_term()), plans=_plans())


@exam_halls_bp.route('/allocate', methods=['GET', 'POST'])
@login_required
def allocate():
    _admin_only()
    if request.method == 'GET':
        return redirect(url_for('exam_halls.index'))
    try:
        # No seed carried in → a new arrangement on every "Allocate"/"Regenerate";
        # the exports re-use the seed so they match what's shown.
        result, payload = _run(request.form)
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('exam_halls.index'))
    sname, branch, term = _masthead()
    return render_template('exam_halls/result.html', result=result, plan=None,
                           school_name=sname, branch=branch, term=term, payload=payload,
                           default_name=_default_name(term))


def _default_name(term):
    from models import local_now
    return 'Exam halls · %s%s' % (local_now().strftime('%d %b %Y'), (' · ' + term) if term else '')


@exam_halls_bp.route('/save', methods=['POST'])
@login_required
def save():
    """Save the arrangement on screen (same seed → identical seats)."""
    _admin_only()
    try:
        result, payload = _run(request.form)
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('exam_halls.index'))
    term = get_active_term()
    name = (request.form.get('plan_name') or '').strip()[:150] or _default_name(term.full_name if term else '')
    plan = ExamHallPlan(branch_id=branch_for_new(), term_id=term.id if term else None, name=name,
                        params=json.dumps(payload), snapshot=json.dumps(_snapshot(result)),
                        total_students=result['total_students'], hall_count=len(result['halls']),
                        created_by=session.get('username') or 'Admin')
    db.session.add(plan)
    db.session.commit()
    from utils.audit import log_action
    log_action('exam_halls.save', f'{name}: {plan.total_students} candidates in {plan.hall_count} halls')
    flash('Saved “%s”.' % name, 'success')
    return redirect(url_for('exam_halls.view_plan', plan_id=plan.id))


@exam_halls_bp.route('/plans/<int:plan_id>')
@login_required
def view_plan(plan_id):
    _admin_only()
    plan = _plan_or_404(plan_id)
    sname, branch, _term = _masthead()
    return render_template('exam_halls/result.html', result=plan.result, plan=plan,
                           school_name=sname, branch=branch,
                           term=plan.term.full_name if plan.term else '', payload=plan.payload,
                           default_name=plan.name)


@exam_halls_bp.route('/plans/<int:plan_id>/rename', methods=['POST'])
@login_required
def rename_plan(plan_id):
    _admin_only()
    plan = _plan_or_404(plan_id)
    name = (request.form.get('plan_name') or '').strip()[:150]
    if name:
        plan.name = name
        db.session.commit()
        flash('Renamed.', 'success')
    return redirect(url_for('exam_halls.view_plan', plan_id=plan.id))


@exam_halls_bp.route('/plans/<int:plan_id>/delete', methods=['POST'])
@login_required
def delete_plan(plan_id):
    _admin_only()
    plan = _plan_or_404(plan_id)
    name = plan.name
    db.session.delete(plan)
    db.session.commit()
    from utils.audit import log_action
    log_action('exam_halls.delete', name)
    flash('Deleted “%s”.' % name, 'success')
    return redirect(url_for('exam_halls.index'))


def _file(result, fmt, name, term):
    from utils import exam_hall_doc
    import re
    stem = re.sub(r'[^A-Za-z0-9]+', '_', name or 'exam_halls').strip('_')[:60] or 'exam_halls'
    if fmt in ('excel', 'xlsx'):
        data = exam_hall_doc.render_xlsx(result, subtitle=name)
        return Response(data, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        headers={'Content-Disposition': f'attachment; filename="{stem}.xlsx"'})
    result = dict(result, term=term)
    data = exam_hall_doc.render_pdf(result, subtitle=name)
    return Response(data, mimetype='application/pdf',
                    headers={'Content-Disposition': f'attachment; filename="{stem}.pdf"'})


@exam_halls_bp.route('/plans/<int:plan_id>/export')
@login_required
def export_plan(plan_id):
    _admin_only()
    plan = _plan_or_404(plan_id)
    return _file(plan.result, (request.args.get('format') or 'pdf').lower(), plan.name,
                 plan.term.full_name if plan.term else '')


@exam_halls_bp.route('/pdf', methods=['POST'])
@login_required
def pdf():
    """Export the (unsaved) arrangement on screen — ``format`` pdf | excel."""
    _admin_only()
    try:
        result, _payload_ = _run(request.form)
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('exam_halls.index'))
    _s, _b, term = _masthead()
    return _file(result, (request.form.get('format') or 'pdf').lower(),
                 (request.form.get('plan_name') or '').strip() or 'Exam hall allocation', term)
