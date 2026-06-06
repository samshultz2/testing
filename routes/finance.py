"""
Finance / Fees routes — fee catalogue, fee structure per class/term, student
payments with printable receipts, discounts/waivers, defaulters and a finance
dashboard.
"""
from datetime import date, datetime

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify)
from sqlalchemy import func

from models import (
    db, FeeItem, FeeStructure, FeePayment, FeeDiscount,
    Student, Term, SchoolClass, ClassArm, AcademicSession,
    StudentEnrollment, ClassArmAssignment,
)
from utils.access_control import (
    login_required, admin_required, is_admin, filter_classes_for_user,
)
from utils.finance import (
    student_bill, structure_items, class_fee_total, student_placement,
    next_receipt_no,
)

finance_bp = Blueprint('finance', __name__, url_prefix='/finance')

PAYMENT_METHODS = ['Cash', 'Bank Transfer', 'POS', 'Cheque', 'Online']


def _active_term_id():
    t = Term.query.filter_by(is_active=True).first()
    return t.id if t else None


def _parse_date(value, default=None):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return default or date.today()


# ============================================================================
# DASHBOARD
# ============================================================================

@finance_bp.route('/')
@login_required
def dashboard():
    term_id = request.args.get('term_id', type=int) or _active_term_id()
    terms = Term.query.order_by(Term.id.desc()).all()
    selected_term = Term.query.get(term_id) if term_id else None

    expected = collected = discounts = 0.0
    by_class = {}            # class_name -> {'expected':, 'collected':}
    method_breakdown = {}
    recent = []
    defaulter_count = 0

    if term_id:
        # Map each enrolled student to their class/arm for this term.
        enrollments = (StudentEnrollment.query
                       .join(ClassArmAssignment,
                             StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
                       .filter(StudentEnrollment.is_active == True,
                               ClassArmAssignment.term_id == term_id).all())

        placement = {}        # student_id -> (class_id, arm_id, class_name)
        total_cache = {}      # (class_id, arm_id) -> per-student fee total
        for e in enrollments:
            asg = e.class_arm_assignment
            key = (asg.class_id, asg.arm_id)
            if key not in total_cache:
                total_cache[key] = class_fee_total(term_id, asg.class_id, asg.arm_id)
            cname = asg.school_class.name if asg.school_class else '—'
            placement[e.student_id] = (asg.class_id, asg.arm_id, cname)
            slot = by_class.setdefault(cname, {'expected': 0.0, 'collected': 0.0})
            slot['expected'] += total_cache[key]
            expected += total_cache[key]

        discounts = (db.session.query(func.coalesce(func.sum(FeeDiscount.amount), 0.0))
                     .filter(FeeDiscount.term_id == term_id).scalar()) or 0.0

        payments = FeePayment.query.filter_by(term_id=term_id).all()
        for p in payments:
            collected += p.amount
            method_breakdown[p.method or 'Other'] = method_breakdown.get(p.method or 'Other', 0.0) + p.amount
            plc = placement.get(p.student_id)
            if plc:
                by_class.setdefault(plc[2], {'expected': 0.0, 'collected': 0.0})['collected'] += p.amount

        recent = (FeePayment.query.filter_by(term_id=term_id)
                  .order_by(FeePayment.created_at.desc()).limit(8).all())

        # Count students with an outstanding balance.
        paid_by_student = {}
        for p in payments:
            paid_by_student[p.student_id] = paid_by_student.get(p.student_id, 0.0) + p.amount
        disc_rows = FeeDiscount.query.filter_by(term_id=term_id).all()
        disc_by_student = {}
        for d in disc_rows:
            disc_by_student[d.student_id] = disc_by_student.get(d.student_id, 0.0) + d.amount
        for sid, (cid, aid, _cn) in placement.items():
            payable = max(total_cache[(cid, aid)] - disc_by_student.get(sid, 0.0), 0)
            if payable - paid_by_student.get(sid, 0.0) > 0.005:
                defaulter_count += 1

    payable_total = max(expected - discounts, 0)
    outstanding = payable_total - collected
    rate = round(collected / payable_total * 100, 1) if payable_total > 0 else 0.0

    class_chart = [{'name': k, 'expected': round(v['expected'], 2),
                    'collected': round(v['collected'], 2)}
                   for k, v in sorted(by_class.items())]
    method_chart = [{'method': k, 'amount': round(v, 2)} for k, v in method_breakdown.items()]

    return render_template('finance/dashboard.html',
        terms=terms, term_id=term_id, selected_term=selected_term,
        expected=expected, collected=collected, discounts=discounts,
        payable_total=payable_total, outstanding=outstanding, rate=rate,
        enrolled=len(placement) if term_id else 0, defaulter_count=defaulter_count,
        class_chart=class_chart, method_chart=method_chart, recent=recent,
        has_structure=(expected > 0),
    )


# ============================================================================
# FEE ITEMS (catalogue)
# ============================================================================

@finance_bp.route('/items')
@login_required
def items_list():
    items = FeeItem.query.order_by(FeeItem.is_active.desc(), FeeItem.name).all()
    return render_template('finance/items.html', items=items)


@finance_bp.route('/items/add', methods=['POST'])
@admin_required
def add_item():
    name = (request.form.get('name') or '').strip()
    if not name:
        flash('Fee item name is required.', 'error')
        return redirect(url_for('finance.items_list'))
    if FeeItem.query.filter(func.lower(FeeItem.name) == name.lower()).first():
        flash(f'"{name}" already exists.', 'warning')
        return redirect(url_for('finance.items_list'))
    db.session.add(FeeItem(name=name, description=(request.form.get('description') or '').strip()))
    db.session.commit()
    flash(f'Added fee item "{name}".', 'success')
    return redirect(url_for('finance.items_list'))


@finance_bp.route('/items/<int:item_id>/edit', methods=['POST'])
@admin_required
def edit_item(item_id):
    item = FeeItem.query.get_or_404(item_id)
    name = (request.form.get('name') or '').strip()
    if name:
        item.name = name
    item.description = (request.form.get('description') or '').strip()
    item.is_active = bool(request.form.get('is_active'))
    db.session.commit()
    flash('Fee item updated.', 'success')
    return redirect(url_for('finance.items_list'))


@finance_bp.route('/items/<int:item_id>/delete', methods=['POST'])
@admin_required
def delete_item(item_id):
    item = FeeItem.query.get_or_404(item_id)
    used = FeeStructure.query.filter_by(fee_item_id=item_id).count()
    if used:
        item.is_active = False
        flash(f'"{item.name}" is used in {used} fee structure row(s); deactivated instead of deleted.', 'info')
    else:
        db.session.delete(item)
        flash('Fee item deleted.', 'success')
    db.session.commit()
    return redirect(url_for('finance.items_list'))


# ============================================================================
# FEE STRUCTURE (amounts per class/term)
# ============================================================================

@finance_bp.route('/structure')
@login_required
def structure():
    term_id = request.args.get('term_id', type=int) or _active_term_id()
    class_id = request.args.get('class_id', type=int)
    arm_id = request.args.get('arm_id', type=int)

    terms = Term.query.order_by(Term.id.desc()).all()
    classes = SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.level).all()
    arms = ClassArm.query.filter_by(is_active=True).order_by(ClassArm.name).all()
    items = FeeItem.query.filter_by(is_active=True).order_by(FeeItem.name).all()

    current = {}
    total = 0.0
    if term_id and class_id:
        rows = FeeStructure.query.filter_by(
            term_id=term_id, class_id=class_id, arm_id=arm_id).all()
        for r in rows:
            current[r.fee_item_id] = r.amount
        total = sum(current.values())

    return render_template('finance/structure.html',
        terms=terms, classes=classes, arms=arms, items=items,
        term_id=term_id, class_id=class_id, arm_id=arm_id,
        current=current, total=total)


@finance_bp.route('/structure/save', methods=['POST'])
@admin_required
def save_structure():
    term_id = request.form.get('term_id', type=int)
    class_id = request.form.get('class_id', type=int)
    arm_id = request.form.get('arm_id', type=int)  # None -> all arms
    if not (term_id and class_id):
        flash('Select a term and class first.', 'error')
        return redirect(url_for('finance.structure'))

    items = FeeItem.query.filter_by(is_active=True).all()
    changed = 0
    for item in items:
        raw = (request.form.get(f'amount_{item.id}') or '').strip()
        existing = FeeStructure.query.filter_by(
            term_id=term_id, class_id=class_id, arm_id=arm_id,
            fee_item_id=item.id).first()
        if raw == '':
            if existing:
                db.session.delete(existing)
                changed += 1
            continue
        try:
            amount = float(raw)
        except ValueError:
            continue
        if amount < 0:
            amount = 0
        if existing:
            if existing.amount != amount:
                existing.amount = amount
                existing.is_active = True
                changed += 1
        else:
            db.session.add(FeeStructure(
                term_id=term_id, class_id=class_id, arm_id=arm_id,
                fee_item_id=item.id, amount=amount))
            changed += 1

    db.session.commit()
    flash(f'Fee structure saved ({changed} change(s)).', 'success')
    return redirect(url_for('finance.structure', term_id=term_id, class_id=class_id, arm_id=arm_id or ''))


@finance_bp.route('/structure/copy', methods=['POST'])
@admin_required
def copy_structure():
    """Copy a whole term's fee structure into another term."""
    from_term_id = request.form.get('from_term_id', type=int)
    to_term_id = request.form.get('to_term_id', type=int)
    if not (from_term_id and to_term_id) or from_term_id == to_term_id:
        flash('Choose two different terms.', 'error')
        return redirect(url_for('finance.structure', term_id=to_term_id))
    src = FeeStructure.query.filter_by(term_id=from_term_id, is_active=True).all()
    copied = skipped = 0
    for r in src:
        exists = FeeStructure.query.filter_by(
            term_id=to_term_id, class_id=r.class_id, arm_id=r.arm_id,
            fee_item_id=r.fee_item_id).first()
        if exists:
            skipped += 1
            continue
        db.session.add(FeeStructure(
            term_id=to_term_id, class_id=r.class_id, arm_id=r.arm_id,
            fee_item_id=r.fee_item_id, amount=r.amount))
        copied += 1
    db.session.commit()
    flash(f'Copied {copied} fee row(s); skipped {skipped} already set.', 'success')
    return redirect(url_for('finance.structure', term_id=to_term_id))


# ============================================================================
# PAYMENTS
# ============================================================================

@finance_bp.route('/payments')
@login_required
def payments_list():
    term_id = request.args.get('term_id', type=int) or _active_term_id()
    class_id = request.args.get('class_id', type=int)
    q = (request.args.get('q') or '').strip()

    terms = Term.query.order_by(Term.id.desc()).all()
    classes = SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.level).all()

    query = FeePayment.query.filter_by(term_id=term_id) if term_id else FeePayment.query
    query = query.join(Student, FeePayment.student_id == Student.id)
    if q:
        like = f'%{q}%'
        query = query.filter(db.or_(Student.surname.ilike(like),
                                    Student.first_name.ilike(like),
                                    Student.student_id.ilike(like),
                                    FeePayment.receipt_no.ilike(like)))
    if class_id and term_id:
        sids = [sid for (sid,) in (StudentEnrollment.query
                .join(ClassArmAssignment,
                      StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
                .filter(StudentEnrollment.is_active == True,
                        ClassArmAssignment.term_id == term_id,
                        ClassArmAssignment.class_id == class_id)
                .with_entities(StudentEnrollment.student_id).all())]
        query = query.filter(FeePayment.student_id.in_(sids or [-1]))

    payments = query.order_by(FeePayment.payment_date.desc(), FeePayment.id.desc()).all()
    total = sum(p.amount for p in payments)

    return render_template('finance/payments.html',
        terms=terms, classes=classes, term_id=term_id, class_id=class_id, q=q,
        payments=payments, total=total)


@finance_bp.route('/payments/record', methods=['GET', 'POST'])
@login_required
def record_payment():
    term_id = request.values.get('term_id', type=int) or _active_term_id()
    student_id = request.values.get('student_id', type=int)

    if request.method == 'POST':
        student_id = request.form.get('student_id', type=int)
        term_id = request.form.get('term_id', type=int)
        amount = request.form.get('amount', type=float)
        if not (student_id and term_id and amount and amount > 0):
            flash('Select a student, term and a positive amount.', 'error')
            return redirect(url_for('finance.record_payment', term_id=term_id, student_id=student_id))
        payment = FeePayment(
            student_id=student_id,
            term_id=term_id,
            amount=amount,
            payment_date=_parse_date(request.form.get('payment_date')),
            method=request.form.get('method') or 'Cash',
            reference=(request.form.get('reference') or '').strip() or None,
            received_by=(request.form.get('received_by') or '').strip() or None,
            notes=(request.form.get('notes') or '').strip() or None,
            receipt_no=next_receipt_no(),
        )
        db.session.add(payment)
        db.session.commit()
        flash(f'Payment recorded — receipt {payment.receipt_no}.', 'success')
        return redirect(url_for('finance.receipt', payment_id=payment.id))

    terms = Term.query.order_by(Term.id.desc()).all()
    student = Student.query.get(student_id) if student_id else None
    bill = student_bill(student_id, term_id) if (student and term_id) else None

    # Class/arm roster picker — lets the user browse a class arm and pick a
    # student (disambiguates students who share a name across arms).
    assignment_id = request.values.get('assignment_id', type=int)
    assignments = []
    if term_id:
        all_assignments = ClassArmAssignment.query.filter_by(term_id=term_id).all()
        assignments = filter_classes_for_user(all_assignments)
        assignments.sort(key=lambda a: a.display_name)
    roster = []
    if term_id and assignment_id and not student:
        enrollments = (StudentEnrollment.query.filter_by(
            class_arm_assignment_id=assignment_id, is_active=True)
            .join(Student).order_by(Student.surname, Student.first_name).all())
        for e in enrollments:
            b = student_bill(e.student_id, term_id)
            roster.append({'student': e.student, 'balance': b['balance'],
                           'paid': b['paid'], 'billed': b['payable']})

    return render_template('finance/record_payment.html',
        terms=terms, term_id=term_id, student=student, bill=bill,
        assignments=assignments, assignment_id=assignment_id, roster=roster,
        methods=PAYMENT_METHODS, today=date.today())


@finance_bp.route('/payments/search')
@login_required
def search_students():
    """JSON student lookup for the payment form."""
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify([])
    term_id = request.args.get('term_id', type=int) or _active_term_id()
    like = f'%{q}%'
    students = (Student.query.filter_by(is_active=True)
                .filter(db.or_(Student.surname.ilike(like),
                               Student.first_name.ilike(like),
                               Student.student_id.ilike(like)))
                .order_by(Student.surname).limit(15).all())
    out = []
    for s in students:
        # Class/arm in the selected term, to tell same-named students apart.
        cls = ''
        enr = (StudentEnrollment.query
               .join(ClassArmAssignment,
                     StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
               .filter(StudentEnrollment.student_id == s.id,
                       StudentEnrollment.is_active == True,
                       ClassArmAssignment.term_id == term_id).first()) if term_id else None
        if enr:
            cls = enr.class_arm_assignment.display_name
        out.append({'id': s.id, 'name': s.full_name, 'sid': s.student_id, 'cls': cls})
    return jsonify(out)


@finance_bp.route('/payments/<int:payment_id>/receipt')
@login_required
def receipt(payment_id):
    payment = FeePayment.query.get_or_404(payment_id)
    bill = student_bill(payment.student_id, payment.term_id)
    from models import SchoolSettings
    school = {
        'name': SchoolSettings.get('school_name', 'My School'),
        'address': SchoolSettings.get('school_address', ''),
        'phone': SchoolSettings.get('school_phone', ''),
        'motto': SchoolSettings.get('school_motto', ''),
    }
    return render_template('finance/receipt.html', payment=payment, bill=bill, school=school)


@finance_bp.route('/payments/<int:payment_id>/delete', methods=['POST'])
@admin_required
def delete_payment(payment_id):
    payment = FeePayment.query.get_or_404(payment_id)
    term_id = payment.term_id
    db.session.delete(payment)
    db.session.commit()
    flash('Payment deleted.', 'success')
    return redirect(url_for('finance.payments_list', term_id=term_id))


# ============================================================================
# STUDENT STATEMENT + DISCOUNTS
# ============================================================================

@finance_bp.route('/students/<int:student_id>/statement')
@login_required
def statement(student_id):
    student = Student.query.get_or_404(student_id)
    term_id = request.args.get('term_id', type=int) or _active_term_id()
    terms = Term.query.order_by(Term.id.desc()).all()
    bill = student_bill(student_id, term_id) if term_id else None
    payments = (FeePayment.query.filter_by(student_id=student_id, term_id=term_id)
                .order_by(FeePayment.payment_date).all()) if term_id else []
    discounts = (FeeDiscount.query.filter_by(student_id=student_id, term_id=term_id)
                 .order_by(FeeDiscount.created_at).all()) if term_id else []
    return render_template('finance/statement.html',
        student=student, terms=terms, term_id=term_id, bill=bill,
        payments=payments, discounts=discounts)


@finance_bp.route('/discounts/add', methods=['POST'])
@admin_required
def add_discount():
    student_id = request.form.get('student_id', type=int)
    term_id = request.form.get('term_id', type=int)
    amount = request.form.get('amount', type=float)
    if not (student_id and term_id and amount and amount > 0):
        flash('A student, term and positive amount are required.', 'error')
        return redirect(url_for('finance.statement', student_id=student_id, term_id=term_id))
    db.session.add(FeeDiscount(
        student_id=student_id, term_id=term_id, amount=amount,
        reason=(request.form.get('reason') or '').strip() or None))
    db.session.commit()
    flash('Discount / waiver applied.', 'success')
    return redirect(url_for('finance.statement', student_id=student_id, term_id=term_id))


@finance_bp.route('/discounts/<int:discount_id>/delete', methods=['POST'])
@admin_required
def delete_discount(discount_id):
    d = FeeDiscount.query.get_or_404(discount_id)
    student_id, term_id = d.student_id, d.term_id
    db.session.delete(d)
    db.session.commit()
    flash('Discount removed.', 'success')
    return redirect(url_for('finance.statement', student_id=student_id, term_id=term_id))


# ============================================================================
# DEFAULTERS / OUTSTANDING
# ============================================================================

@finance_bp.route('/defaulters')
@login_required
def defaulters():
    term_id = request.args.get('term_id', type=int) or _active_term_id()
    class_id = request.args.get('class_id', type=int)
    terms = Term.query.order_by(Term.id.desc()).all()
    classes = SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.level).all()

    rows = []
    totals = {'billed': 0.0, 'paid': 0.0, 'balance': 0.0}
    if term_id:
        enr_q = (StudentEnrollment.query
                 .join(ClassArmAssignment,
                       StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
                 .filter(StudentEnrollment.is_active == True,
                         ClassArmAssignment.term_id == term_id))
        if class_id:
            enr_q = enr_q.filter(ClassArmAssignment.class_id == class_id)
        enrollments = enr_q.all()

        # Pre-aggregate payments + discounts for the term.
        paid_map = dict(db.session.query(FeePayment.student_id, func.sum(FeePayment.amount))
                        .filter(FeePayment.term_id == term_id)
                        .group_by(FeePayment.student_id).all())
        disc_map = dict(db.session.query(FeeDiscount.student_id, func.sum(FeeDiscount.amount))
                        .filter(FeeDiscount.term_id == term_id)
                        .group_by(FeeDiscount.student_id).all())
        total_cache = {}
        for e in enrollments:
            asg = e.class_arm_assignment
            key = (asg.class_id, asg.arm_id)
            if key not in total_cache:
                total_cache[key] = class_fee_total(term_id, asg.class_id, asg.arm_id)
            billed = total_cache[key]
            payable = max(billed - (disc_map.get(e.student_id) or 0.0), 0)
            paid = paid_map.get(e.student_id) or 0.0
            balance = payable - paid
            if balance > 0.005:
                rows.append({
                    'student': e.student,
                    'class_name': asg.school_class.name if asg.school_class else '—',
                    'arm_name': asg.arm.name if asg.arm else '',
                    'billed': payable, 'paid': paid, 'balance': balance,
                })
                totals['billed'] += payable
                totals['paid'] += paid
                totals['balance'] += balance
        rows.sort(key=lambda r: r['balance'], reverse=True)

    return render_template('finance/defaulters.html',
        terms=terms, classes=classes, term_id=term_id, class_id=class_id,
        rows=rows, totals=totals)
