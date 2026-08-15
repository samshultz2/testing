"""Student welfare — discipline/incident log and sick bay (clinic) visits.

Recorded from the student profile. Branch-scoped like the rest of the app.
"""
from datetime import date
from utils import timeutil

from flask import Blueprint, request, redirect, url_for, flash, session

from models import db, Student, DisciplineRecord, ClinicVisit
from utils.access_control import login_required
from utils.branch_scope import require_branch_access, branch_for_new
from utils.helpers import parse_date
from utils.audit import log_action

welfare_bp = Blueprint('welfare', __name__, url_prefix='/welfare')

DISCIPLINE_CATEGORIES = ['Lateness', 'Truancy', 'Uniform', 'Fighting', 'Rudeness',
                         'Bullying', 'Property damage', 'Exam misconduct', 'Other']


def _student_or_404(student_id):
    s = db.get_or_404(Student, student_id)
    require_branch_access(s.branch_id)
    return s


@welfare_bp.route('/discipline/<int:student_id>/add', methods=['POST'])
@login_required
def add_discipline(student_id):
    s = _student_or_404(student_id)
    desc = (request.form.get('description') or '').strip()
    if not desc:
        flash('A description is required.', 'error')
        return redirect(url_for('main.view_student', student_id=s.id))
    db.session.add(DisciplineRecord(
        student_id=s.id, branch_id=s.branch_id or branch_for_new(),
        date=parse_date(request.form.get('date')) or timeutil.today(),
        category=request.form.get('category') or None,
        severity=request.form.get('severity') or None,
        description=desc,
        action_taken=(request.form.get('action_taken') or '').strip() or None,
        reported_by=session.get('user') or 'Staff'))
    db.session.commit()
    log_action('welfare.discipline_add', target=s)
    flash('Discipline record added.', 'success')
    return redirect(url_for('main.view_student', student_id=s.id))


@welfare_bp.route('/discipline/<int:record_id>/delete', methods=['POST'])
@login_required
def delete_discipline(record_id):
    rec = db.get_or_404(DisciplineRecord, record_id)
    require_branch_access(rec.branch_id)
    sid = rec.student_id
    db.session.delete(rec); db.session.commit()
    flash('Discipline record removed.', 'success')
    return redirect(url_for('main.view_student', student_id=sid))


@welfare_bp.route('/clinic/<int:student_id>/add', methods=['POST'])
@login_required
def add_clinic(student_id):
    s = _student_or_404(student_id)
    complaint = (request.form.get('complaint') or '').strip()
    if not complaint:
        flash('A complaint/symptom is required.', 'error')
        return redirect(url_for('main.view_student', student_id=s.id))
    db.session.add(ClinicVisit(
        student_id=s.id, branch_id=s.branch_id or branch_for_new(),
        date=parse_date(request.form.get('date')) or timeutil.today(),
        complaint=complaint,
        treatment=(request.form.get('treatment') or '').strip() or None,
        parent_notified=request.form.get('parent_notified') == 'on',
        attended_by=session.get('user') or 'Staff'))
    db.session.commit()
    log_action('welfare.clinic_add', target=s)
    flash('Clinic visit recorded.', 'success')
    return redirect(url_for('main.view_student', student_id=s.id))


@welfare_bp.route('/clinic/<int:visit_id>/delete', methods=['POST'])
@login_required
def delete_clinic(visit_id):
    v = db.get_or_404(ClinicVisit, visit_id)
    require_branch_access(v.branch_id)
    sid = v.student_id
    db.session.delete(v); db.session.commit()
    flash('Clinic visit removed.', 'success')
    return redirect(url_for('main.view_student', student_id=sid))
