"""Study/Project Groups (Tools): group a class's students for group work,
weighted by their performance the previous term -- the strongest performers
become group leaders so every group gets a similar mix of ability. New
students (or ones with no usable previous-term data) are placed randomly.
Arms can be merged for this tool only -- it never touches
ClassArmAssignment/StudentEnrollment, just widens the candidate pool.
"""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify)

from models import (db, SchoolClass, ClassArm, ClassArmAssignment, StudentEnrollment,
                    Term, GroupSet, StudentGroup, GroupMember, Student)
from utils.access_control import login_required
from utils.branch_scope import scope_query, require_branch_access, branch_for_new, viewing_branch_id
from utils.helpers import get_active_term
from utils import study_groups as sg

study_groups_bp = Blueprint('study_groups', __name__, url_prefix='/tools/study-groups')


def _current_user():
    from flask import session
    return session.get('username') or session.get('user') or 'Admin'


def _classes_with_arm_counts(term):
    """Active classes for the active term, each with its arms + active
    student count per arm -- branch-scoped, only arms that actually have
    students are worth showing."""
    if not term:
        return []
    assignments = scope_query(ClassArmAssignment.query.filter_by(term_id=term.id),
                              ClassArmAssignment).all()
    if not assignments:
        return []
    from sqlalchemy import func
    counts = dict(db.session.query(
            StudentEnrollment.class_arm_assignment_id, func.count(StudentEnrollment.id))
        .filter(StudentEnrollment.class_arm_assignment_id.in_([a.id for a in assignments]),
                StudentEnrollment.is_active.is_(True))
        .group_by(StudentEnrollment.class_arm_assignment_id).all())
    by_class = {}
    for a in assignments:
        count = counts.get(a.id, 0)
        if not count or not a.school_class:
            continue
        entry = by_class.setdefault(a.class_id, {'id': a.class_id, 'name': a.school_class.name,
                                                 'level': a.school_class.level, 'arms': []})
        entry['arms'].append({'id': a.arm_id, 'name': a.arm_label or ClassArm.DEFAULT_NAME,
                              'count': count})
    rows = sorted(by_class.values(), key=lambda r: (r['level'], r['name']))
    for r in rows:
        r['arms'].sort(key=lambda a: a['name'])
        r['total'] = sum(a['count'] for a in r['arms'])
    return rows


def _set_or_404(set_id):
    gs = db.get_or_404(GroupSet, set_id)
    require_branch_access(gs.branch_id)
    return gs


def _set_payload(gs):
    """JSON-friendly snapshot of a GroupSet for the view/edit page."""
    groups = []
    for g in gs.groups:
        members = []
        for m in g.members:
            members.append({
                'student_id': m.student_id,
                'name': m.student.full_name if m.student else f'#{m.student_id}',
                'admission_no': m.student.student_id if m.student else '',
                'basis_average': m.basis_average,
                'is_leader': g.leader_student_id == m.student_id,
            })
        members.sort(key=lambda mm: (not mm['is_leader'], mm['name']))
        groups.append({'id': g.id, 'position': g.position, 'label': g.display_label,
                       'leader_student_id': g.leader_student_id, 'members': members})
    return {
        'id': gs.id, 'title': gs.title, 'class_name': gs.school_class.name if gs.school_class else '',
        'term_name': gs.term.full_name if gs.term else '',
        'basis_term_name': gs.basis_term.full_name if gs.basis_term else None,
        'group_size': gs.group_size, 'num_groups': gs.num_groups,
        'created_by': gs.created_by,
        'created_at': gs.created_at.strftime('%d %b %Y %H:%M') if gs.created_at else '',
        'groups': groups,
        'urls': {
            'move': url_for('study_groups.move_member', set_id=gs.id),
            'leader': url_for('study_groups.set_group_leader', set_id=gs.id),
            'rename': url_for('study_groups.rename_group', set_id=gs.id),
            'rename_set': url_for('study_groups.rename_set', set_id=gs.id),
            'pdf': url_for('study_groups.export_pdf', set_id=gs.id),
            'xlsx': url_for('study_groups.export_xlsx', set_id=gs.id),
            'png': url_for('study_groups.export_png', set_id=gs.id),
            'delete': url_for('study_groups.delete_set', set_id=gs.id),
            'index': url_for('study_groups.index'),
        },
    }


@study_groups_bp.route('/')
@login_required
def index():
    term = get_active_term()
    classes = _classes_with_arm_counts(term)
    sets = (scope_query(GroupSet.query, GroupSet)
           .order_by(GroupSet.created_at.desc()).limit(50).all())
    recent = [{'id': s.id, 'title': s.title or f'Set #{s.id}',
              'class_name': s.school_class.name if s.school_class else '',
              'num_groups': s.num_groups, 'group_size': s.group_size,
              'created_at': s.created_at.strftime('%d %b %Y') if s.created_at else '',
              'url': url_for('study_groups.view_set', set_id=s.id)} for s in sets]
    return render_template('study_groups/index.html', classes=classes, has_term=bool(term),
                           recent=recent)


@study_groups_bp.route('/generate', methods=['POST'])
@login_required
def generate():
    class_id = request.form.get('class_id', type=int)
    arm_ids = [int(x) for x in request.form.getlist('arm_ids[]') if x]
    group_size = request.form.get('group_size', type=int)
    title = (request.form.get('title') or '').strip() or None
    term = get_active_term()

    if not term:
        flash('No active term is set.', 'error')
        return redirect(url_for('study_groups.index'))
    if not class_id or not arm_ids:
        flash('Pick a class and at least one arm.', 'error')
        return redirect(url_for('study_groups.index'))
    if not group_size or group_size < 1:
        flash('Enter how many students per group (1 or more).', 'error')
        return redirect(url_for('study_groups.index'))

    cls = db.session.get(SchoolClass, class_id)
    if not cls:
        flash('Class not found.', 'error')
        return redirect(url_for('study_groups.index'))

    branch_id = branch_for_new()
    try:
        gs = sg.create_group_set(branch_id=branch_id, class_id=class_id, arm_ids=arm_ids,
                                 term_id=term.id, group_size=group_size, title=title,
                                 created_by=_current_user())
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('study_groups.index'))

    flash(f'{gs.num_groups} group(s) created for {cls.name}.', 'success')
    return redirect(url_for('study_groups.view_set', set_id=gs.id))


@study_groups_bp.route('/<int:set_id>')
@login_required
def view_set(set_id):
    gs = _set_or_404(set_id)
    return render_template('study_groups/view.html', data=_set_payload(gs))


@study_groups_bp.route('/<int:set_id>/move', methods=['POST'])
@login_required
def move_member(set_id):
    gs = _set_or_404(set_id)
    student_id = request.form.get('student_id', type=int)
    group_id = request.form.get('group_id', type=int)
    try:
        sg.move_student(gs.id, student_id, group_id)
    except ValueError as e:
        if request.headers.get('X-Requested-With') == 'fetch':
            return jsonify(ok=False, error=str(e)), 400
        flash(str(e), 'error')
        return redirect(url_for('study_groups.view_set', set_id=set_id))
    if request.headers.get('X-Requested-With') == 'fetch':
        return jsonify(ok=True, data=_set_payload(gs))
    return redirect(url_for('study_groups.view_set', set_id=set_id))


@study_groups_bp.route('/<int:set_id>/leader', methods=['POST'])
@login_required
def set_group_leader(set_id):
    gs = _set_or_404(set_id)
    group_id = request.form.get('group_id', type=int)
    student_id = request.form.get('student_id', type=int)
    try:
        sg.set_leader(gs.id, group_id, student_id)
    except ValueError as e:
        if request.headers.get('X-Requested-With') == 'fetch':
            return jsonify(ok=False, error=str(e)), 400
        flash(str(e), 'error')
        return redirect(url_for('study_groups.view_set', set_id=set_id))
    if request.headers.get('X-Requested-With') == 'fetch':
        return jsonify(ok=True, data=_set_payload(gs))
    return redirect(url_for('study_groups.view_set', set_id=set_id))


@study_groups_bp.route('/<int:set_id>/rename', methods=['POST'])
@login_required
def rename_group(set_id):
    gs = _set_or_404(set_id)
    group_id = request.form.get('group_id', type=int)
    label = (request.form.get('label') or '').strip()[:80]
    group = StudentGroup.query.filter_by(id=group_id, group_set_id=gs.id).first()
    if not group:
        return jsonify(ok=False, error='Group not found.'), 404
    group.label = label or None
    db.session.commit()
    return jsonify(ok=True, label=group.display_label)


@study_groups_bp.route('/<int:set_id>/rename-set', methods=['POST'])
@login_required
def rename_set(set_id):
    gs = _set_or_404(set_id)
    title = (request.form.get('title') or '').strip()[:120]
    gs.title = title or None
    db.session.commit()
    if request.headers.get('X-Requested-With') == 'fetch':
        return jsonify(ok=True, title=gs.title)
    flash('Group set renamed.', 'success')
    return redirect(url_for('study_groups.view_set', set_id=set_id))


@study_groups_bp.route('/<int:set_id>/delete', methods=['POST'])
@login_required
def delete_set(set_id):
    gs = _set_or_404(set_id)
    db.session.delete(gs)
    db.session.commit()
    flash('Group set deleted.', 'success')
    return redirect(url_for('study_groups.index'))


@study_groups_bp.route('/<int:set_id>/export.pdf')
@login_required
def export_pdf(set_id):
    gs = _set_or_404(set_id)
    from utils.study_groups_export import build_pdf
    from utils.web_exports import pdf_response
    from utils.school import school_profile
    buf = build_pdf(_set_payload(gs), school_profile() or {})
    return pdf_response(buf, f'{(gs.title or "study-groups")}.pdf')


@study_groups_bp.route('/<int:set_id>/export.xlsx')
@login_required
def export_xlsx(set_id):
    gs = _set_or_404(set_id)
    from utils.study_groups_export import build_xlsx
    from utils.web_exports import xlsx_response
    buf = build_xlsx(_set_payload(gs))
    return xlsx_response(buf, f'{(gs.title or "study-groups")}.xlsx')


@study_groups_bp.route('/<int:set_id>/export.png')
@login_required
def export_png(set_id):
    gs = _set_or_404(set_id)
    from utils.study_groups_export import build_png
    from utils.web_exports import png_response
    from utils.school import school_profile
    buf = build_png(_set_payload(gs), school_profile() or {})
    return png_response(buf, f'{(gs.title or "study-groups")}.png', inline=False)
