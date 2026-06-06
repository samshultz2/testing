"""
Admissions routes — applicant pipeline, screening/decisions, one-click
conversion of an admitted applicant into a Student, dashboard and CSV export.
"""
from datetime import datetime, date
import csv
import io

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, Response)
from sqlalchemy import func

from models import (db, Applicant, AcademicSession, SchoolClass, ClassArm,
                    ClassArmAssignment, Student)
from utils.access_control import login_required, admin_required, is_admin
from utils import admissions

adm_bp = Blueprint('admissions', __name__, url_prefix='/admissions')


def _d(value, default=None):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return default


def _active_session():
    return AcademicSession.query.filter_by(is_active=True).first()


# ============================================================================
# DASHBOARD
# ============================================================================

@adm_bp.route('/')
@login_required
def dashboard():
    session_id = request.args.get('session_id', type=int)
    sessions = AcademicSession.query.order_by(AcademicSession.name.desc()).all()
    stats = admissions.pipeline_stats(session_id)
    recent = (Applicant.query.order_by(Applicant.created_at.desc()).limit(8).all())
    # by intended class
    cls_rows = (db.session.query(SchoolClass.name, func.count(Applicant.id))
                .join(Applicant, Applicant.intended_class_id == SchoolClass.id)
                .group_by(SchoolClass.name).all())
    class_chart = [{'name': n, 'count': c} for n, c in cls_rows]
    return render_template('admissions/dashboard.html', stats=stats, recent=recent,
        sessions=sessions, session_id=session_id, class_chart=class_chart,
        status_badge=admissions.STATUS_BADGE)


# ============================================================================
# APPLICANTS
# ============================================================================

@adm_bp.route('/applicants')
@login_required
def applicants():
    status = request.args.get('status')
    session_id = request.args.get('session_id', type=int)
    class_id = request.args.get('class_id', type=int)
    q = (request.args.get('q') or '').strip()

    query = Applicant.query
    if status:
        query = query.filter_by(status=status)
    if session_id:
        query = query.filter_by(session_id=session_id)
    if class_id:
        query = query.filter_by(intended_class_id=class_id)
    if q:
        like = f'%{q}%'
        query = query.filter(db.or_(Applicant.first_name.ilike(like),
                                    Applicant.surname.ilike(like),
                                    Applicant.application_no.ilike(like),
                                    Applicant.parent_phone.ilike(like)))
    rows = query.order_by(Applicant.created_at.desc()).all()
    return render_template('admissions/applicants.html', rows=rows,
        sessions=AcademicSession.query.order_by(AcademicSession.name.desc()).all(),
        classes=SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.level).all(),
        status=status, session_id=session_id, class_id=class_id, q=q,
        statuses=admissions.ALL_STATUSES, status_badge=admissions.STATUS_BADGE)


def _read_form(a):
    a.first_name = (request.form.get('first_name') or '').strip()
    a.surname = (request.form.get('surname') or '').strip()
    a.middle_name = (request.form.get('middle_name') or '').strip() or None
    a.gender = request.form.get('gender') or None
    a.date_of_birth = _d(request.form.get('date_of_birth'))
    a.session_id = request.form.get('session_id', type=int) or None
    a.intended_class_id = request.form.get('intended_class_id', type=int) or None
    a.previous_school = (request.form.get('previous_school') or '').strip() or None
    a.source = request.form.get('source') or None
    a.entrance_score = request.form.get('entrance_score', type=float)
    a.parent_name = (request.form.get('parent_name') or '').strip() or None
    a.parent_phone = (request.form.get('parent_phone') or '').strip() or None
    a.parent_email = (request.form.get('parent_email') or '').strip() or None
    a.relationship = (request.form.get('relationship') or '').strip() or None
    a.address = (request.form.get('address') or '').strip() or None
    a.notes = (request.form.get('notes') or '').strip() or None


@adm_bp.route('/applicants/add', methods=['GET', 'POST'])
@login_required
def add_applicant():
    if request.method == 'POST':
        if not (request.form.get('first_name') and request.form.get('surname')):
            flash('First name and surname are required.', 'error')
            return redirect(url_for('admissions.add_applicant'))
        a = Applicant(application_no=Applicant.generate_application_no(),
                      status=request.form.get('status') or 'Applied',
                      applied_date=date.today())
        _read_form(a)
        db.session.add(a)
        db.session.commit()
        flash(f'Application {a.application_no} created for {a.full_name}.', 'success')
        return redirect(url_for('admissions.applicant_detail', applicant_id=a.id))
    return render_template('admissions/applicant_form.html', a=None,
        sessions=AcademicSession.query.order_by(AcademicSession.name.desc()).all(),
        classes=SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.level).all(),
        active_session=_active_session(), sources=admissions.SOURCES,
        statuses=admissions.ALL_STATUSES)


@adm_bp.route('/applicants/<int:applicant_id>')
@login_required
def applicant_detail(applicant_id):
    a = Applicant.query.get_or_404(applicant_id)
    # class arms for the intended class (for enrolment on conversion)
    assignments = []
    if a.intended_class_id:
        aq = ClassArmAssignment.query.filter_by(class_id=a.intended_class_id)
        if a.session_id:
            from models import Term
            term_ids = [t.id for t in Term.query.filter_by(session_id=a.session_id).all()]
            if term_ids:
                aq = aq.filter(ClassArmAssignment.term_id.in_(term_ids))
        assignments = aq.all()
    return render_template('admissions/applicant_detail.html', a=a,
        stages=admissions.STAGES, outcomes=admissions.OUTCOMES,
        status_badge=admissions.STATUS_BADGE, assignments=assignments)


@adm_bp.route('/applicants/<int:applicant_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_applicant(applicant_id):
    a = Applicant.query.get_or_404(applicant_id)
    if request.method == 'POST':
        _read_form(a)
        db.session.commit()
        flash('Application updated.', 'success')
        return redirect(url_for('admissions.applicant_detail', applicant_id=a.id))
    return render_template('admissions/applicant_form.html', a=a,
        sessions=AcademicSession.query.order_by(AcademicSession.name.desc()).all(),
        classes=SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.level).all(),
        active_session=_active_session(), sources=admissions.SOURCES,
        statuses=admissions.ALL_STATUSES)


@adm_bp.route('/applicants/<int:applicant_id>/status', methods=['POST'])
@login_required
def set_status(applicant_id):
    a = Applicant.query.get_or_404(applicant_id)
    new_status = request.form.get('status')
    if new_status in admissions.ALL_STATUSES:
        a.status = new_status
        if new_status in ('Rejected', 'Admitted', 'Accepted', 'Offered'):
            a.decision_date = date.today()
        score = request.form.get('entrance_score', type=float)
        if score is not None:
            a.entrance_score = score
        db.session.commit()
        flash(f'Status set to {new_status}.', 'success')
    return redirect(url_for('admissions.applicant_detail', applicant_id=applicant_id))


@adm_bp.route('/applicants/<int:applicant_id>/convert', methods=['POST'])
@admin_required
def convert(applicant_id):
    a = Applicant.query.get_or_404(applicant_id)
    student, err = admissions.convert_to_student(a, request.form.get('assignment_id', type=int))
    if err and not student:
        flash(err, 'error')
        return redirect(url_for('admissions.applicant_detail', applicant_id=applicant_id))
    if err:
        flash(err, 'info')
    else:
        flash(f'{a.full_name} admitted as student {student.student_id}.', 'success')
    return redirect(url_for('main.view_student', student_id=student.id))


@adm_bp.route('/applicants/<int:applicant_id>/delete', methods=['POST'])
@admin_required
def delete_applicant(applicant_id):
    a = Applicant.query.get_or_404(applicant_id)
    db.session.delete(a)
    db.session.commit()
    flash('Application deleted.', 'success')
    return redirect(url_for('admissions.applicants'))


@adm_bp.route('/export')
@login_required
def export():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['Application No', 'Name', 'Gender', 'Intended Class', 'Session',
                'Status', 'Entrance Score', 'Parent', 'Phone', 'Applied'])
    for a in Applicant.query.order_by(Applicant.created_at.desc()).all():
        w.writerow([a.application_no, a.full_name, a.gender or '',
                    a.intended_class.name if a.intended_class else '',
                    a.session.name if a.session else '', a.status,
                    a.entrance_score if a.entrance_score is not None else '',
                    a.parent_name or '', a.parent_phone or '',
                    a.applied_date or ''])
    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=applicants.csv'})
