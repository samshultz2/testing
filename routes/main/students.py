"""main blueprint — students routes (split from the former routes/main.py)."""
from routes.main import *  # noqa: F401,F403  (blueprint, models, helpers)
from utils.search import like_term
from utils.security import strip_tags


# Fields whose edits are worth an audit trail with their previous value. The
# three sensitive ones (encrypted at rest) are audited as "changed" only — we
# never copy their plaintext into the append-only log.
_AUDIT_STUDENT_FIELDS = {
    'first_name': 'First name', 'middle_name': 'Middle name', 'surname': 'Surname',
    'gender': 'Gender', 'date_of_birth': 'Date of birth', 'religion': 'Religion',
    'stream': 'Stream', 'jamb_target': 'JAMB target',
    'waec_subjects': 'WAEC subjects', 'jamb_subjects': 'JAMB subjects',
    'house': 'House', 'boarding_status': 'Boarding status',
    'nin': 'NIN', 'jamb_reg_number': 'JAMB reg number', 'jamb_profile_code': 'JAMB profile code',
    'waec_reg_number': 'WAEC reg number', 'serial_number': 'Serial number',
    'blood_group': 'Blood group', 'genotype': 'Genotype', 'allergies': 'Allergies',
    'medical_conditions': 'Medical conditions', 'disabilities': 'Disabilities',
    'medications': 'Medications',
    'home_address': 'Home address', 'medical_notes': 'Medical notes',
    'emergency_medical': 'Emergency medical',
}
_AUDIT_STUDENT_SENSITIVE = {'home_address', 'medical_notes', 'emergency_medical'}


def _snapshot_student(student):
    """Capture the audited fields' values before an edit, so the change summary
    can show previous → new."""
    return {f: getattr(student, f, None) for f in _AUDIT_STUDENT_FIELDS}


def _student_change_detail(before, student):
    """Human 'Label: "old" → "new"' summary of what an edit changed, for the
    audit log. Sensitive fields are reported as changed without their values;
    returns '' when nothing tracked changed."""
    def norm(v):
        return None if (v is None or v == '') else v

    def fmt(v):
        return f'"{v}"' if norm(v) is not None else '(empty)'

    parts = []
    for f, label in _AUDIT_STUDENT_FIELDS.items():
        old, new = norm(before.get(f)), norm(getattr(student, f, None))
        if old == new:
            continue
        if f in _AUDIT_STUDENT_SENSITIVE:
            parts.append(f'{label}: changed')
        else:
            parts.append(f'{label}: {fmt(old)} → {fmt(new)}')
    return '; '.join(parts)


@main_bp.route('/students')
@login_required
def students_list():
    """Students list — React app, hydrated inline with the first (scoped,
    filtered) page so it renders instantly and works offline; subsequent
    filter/page changes call /api/students."""
    return render_template('students/list.html', students_json=_students_payload())


@main_bp.route('/api/students')
@login_required
def api_students():
    """Students list as JSON for the React list — same scope/filters/sort as
    the page (via _students_query), paginated, plus the filter option lists."""
    return jsonify(_students_payload())


@main_bp.route('/students/add', methods=['GET', 'POST'])
@login_required
def add_student():
    """Add a new student"""
    if request.method == 'POST':
        try:
            # Create student
            student = Student(
                student_id=Student.generate_student_id(),
                first_name=strip_tags(request.form.get('first_name')),
                middle_name=strip_tags(request.form.get('middle_name')) or None,
                surname=strip_tags(request.form.get('surname')),
                gender=request.form.get('gender'),
                date_of_birth=parse_date(request.form.get('date_of_birth')),
                religion=request.form.get('religion'),
                home_address=request.form.get('home_address', '').strip() or None,
                hobbies=request.form.get('hobbies', '').strip() or None,
                waec_subjects=', '.join(request.form.getlist('waec_subjects[]')) or None,
                jamb_subjects=', '.join(request.form.getlist('jamb_subjects[]')) or None,
                stream=request.form.get('stream') or None,
                jamb_target=request.form.get('jamb_target', type=int)
            )
            # Stamp the student with the creator's (or chosen) branch.
            from utils.branch_scope import branch_for_new
            student.branch_id = branch_for_new(request.form.get('branch_id', type=int))
            _apply_optional_student_fields(student, request.form)

            db.session.add(student)
            db.session.flush()

            # Add parent contacts
            phone_numbers = request.form.getlist('phone_number[]')
            relationships = request.form.getlist('relationship[]')
            contact_names = request.form.getlist('contact_name[]')
            contact_emails = request.form.getlist('email[]')

            for i, phone in enumerate(phone_numbers):
                if phone.strip():
                    contact = ParentContact(
                        student_id=student.id,
                        phone_number=phone.strip(),
                        email=(contact_emails[i].strip() if i < len(contact_emails) and contact_emails[i].strip() else None),
                        relationship=relationships[i] if i < len(relationships) else 'Guardian',
                        name=contact_names[i] if i < len(contact_names) else None,
                        is_primary=(i == 0)
                    )
                    db.session.add(contact)

            # Enrol the student into a class+arm for the active term. A form
            # teacher who doesn't pick a class gets their own form class by
            # default, so "a teacher adds a student" lands them in the right
            # class automatically.
            enrolled_label = None
            from utils.access_control import (get_teacher_profile, can_access_class,
                                              filter_classes_for_user)
            caa_id = request.form.get('class_arm_assignment_id', type=int)
            active_term = get_active_term()
            teacher = get_teacher_profile()
            if not caa_id and teacher and not is_admin() and active_term:
                form_ids = list(teacher.form_class_ids or [])
                if form_ids:
                    match = (ClassArmAssignment.query
                             .filter(ClassArmAssignment.term_id == active_term.id,
                                     ClassArmAssignment.id.in_(form_ids)).first())
                    if match:
                        caa_id = match.id
            if caa_id:
                caa = db.session.get(ClassArmAssignment, caa_id)
                if caa and can_access_class(caa.id):
                    exists = StudentEnrollment.query.filter_by(
                        student_id=student.id, class_arm_assignment_id=caa.id).first()
                    if not exists:
                        db.session.add(StudentEnrollment(
                            student_id=student.id, class_arm_assignment_id=caa.id,
                            is_active=True))
                    enrolled_label = caa.display_name

            db.session.commit()
            log_action('student.create', target=student)
            view_url = url_for('main.view_student', student_id=student.id)
            from utils.notify import notify_student_change
            notify_student_change('create', student=student, url=view_url)
            if enrolled_label:
                flash(f'{FlashMessages.STUDENT_CREATED} Enrolled in {enrolled_label}.', 'success')
            else:
                flash(FlashMessages.STUDENT_CREATED, 'success')
            if _wants_json():
                return jsonify({'ok': True, 'redirect': view_url})
            return redirect(view_url)

        except Exception as e:
            db.session.rollback()
            if _wants_json():
                return jsonify({'ok': False, 'error': f'Error creating student: {e}'}), 400
            flash(f'Error creating student: {str(e)}', 'error')

    payload = {
        'mode': 'add',
        'student': {'gender': '', 'waec_subjects': [], 'jamb_subjects': []},
        'contacts': [_blank_contact()],
        'options': _student_form_options(with_enrolment=True),
        'urls': {'submit': url_for('main.add_student'),
                 'cancel': url_for('main.students_list')},
    }
    return render_template('students/add.html', form_json=payload)


@main_bp.route('/students/import', methods=['POST'])
@login_required
def import_students():
    """Create many students from pasted text (reuses the shared row importer).

    Same endpoint, two modes: without a truthy ``commit`` flag it returns a
    dry-run *preview*; with it, the rows are actually saved. Only some headings
    need be present (at least Surname + First Name); unknown columns are ignored
    and missing ones left blank. Teachers (read-only list) may not import.
    """
    from utils.excel_utils import (rows_from_pasted_text, preview_student_rows,
                                   import_student_rows)
    if is_teacher():
        return jsonify({'ok': False, 'error': 'You do not have permission to import students.'}), 403

    text = (request.json or {}).get('text', '') if request.is_json else request.form.get('text', '')
    rows = rows_from_pasted_text(text)
    if not rows or len(rows) < 2:
        return jsonify({'ok': False, 'error': 'Paste a heading row and at least one student.'}), 400

    prev = preview_student_rows(rows)
    if 'surname' not in prev['recognised'] and 'first_name' not in prev['recognised']:
        return jsonify({'ok': False, 'error': 'Could not find a name column. '
                        'Include at least a "Surname" or "First Name" heading.'}), 400

    commit = request.form.get('commit') in ('1', 'true', 'on', 'yes')
    if not commit:
        return jsonify({
            'ok': True, 'preview': True,
            'recognised': prev['recognised'], 'ignored': prev['ignored'],
            'total': prev['total'], 'valid': prev['valid'], 'invalid': prev['invalid'],
            # Cap the echoed rows so a huge paste doesn't bloat the response.
            'rows': prev['rows'][:200], 'truncated': len(prev['rows']) > 200,
        })

    # ---- commit ----------------------------------------------------------
    from utils.branch_scope import branch_for_new
    from utils.access_control import can_access_class
    new_branch_id = branch_for_new(request.form.get('branch_id', type=int))

    caa = None
    caa_id = request.form.get('class_arm_assignment_id', type=int)
    if caa_id:
        caa = db.session.get(ClassArmAssignment, caa_id)
        if not caa or not can_access_class(caa.id):
            caa = None

    created, messages = import_student_rows(
        rows, db, Student, ParentContact, branch_id=new_branch_id,
        class_arm_assignment_id=caa.id if caa else None)
    if created:
        log_action('student.import', detail=f'Imported {created} students')
        from utils.notify import notify_student_change
        notify_student_change('import', detail=f'{created} student(s) imported',
                              url=url_for('main.students_list'))
        flash(f'Imported {created} student(s).'
              + (f' Enrolled in {caa.display_name}.' if caa else ''), 'success')
    return jsonify({'ok': True, 'created': created, 'messages': messages,
                    'redirect': url_for('main.students_list')})


@main_bp.route('/students/<int:student_id>')
@login_required
def view_student(student_id):
    """Student detail — React app, hydrated inline with the full record."""
    student, err = _student_or_redirect(student_id)
    if err:
        flash(err[1], 'error')
        return redirect(url_for('main.students_list'))
    return render_template('students/view.html', student_json=_student_view_payload(student),
                           student_name=student.full_name)


@main_bp.route('/api/students/<int:student_id>')
@login_required
def api_student_view(student_id):
    """Student detail as JSON (scoped like the page) — used to refresh the view
    after adding/removing a welfare record without a full reload."""
    student, err = _student_or_redirect(student_id)
    if err:
        return jsonify({'error': err[1]}), 403
    return jsonify(_student_view_payload(student))


@main_bp.route('/students/<int:student_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_student(student_id):
    """Edit student details"""
    # Same scope as viewing: branch-scoped and a form teacher is limited to
    # their own students (a teacher can't edit another class's student by URL).
    student, err = _student_or_redirect(student_id)
    if err:
        if _wants_json():
            return jsonify({'ok': False, 'error': err[1]}), 403
        if err[0] == 'branch':
            abort(403)   # cross-branch edit is an IDOR attempt, not a redirect
        flash(err[1], 'error')
        return redirect(url_for('main.students_list'))

    if request.method == 'POST':
        try:
            # When the full edit form is submitted, fields absent from the POST
            # mean "cleared"; for any other (partial/programmatic) POST we only
            # touch fields that are actually present, so nothing gets blanked
            # accidentally.
            complete = request.form.get('form_complete') == '1'
            form = request.form
            before = _snapshot_student(student)   # for the audit change summary

            def has(key):
                return complete or key in form

            if has('first_name'):
                student.first_name = strip_tags(form.get('first_name'))
            if has('surname'):
                student.surname = strip_tags(form.get('surname'))
            if has('middle_name'):
                student.middle_name = strip_tags(form.get('middle_name')) or None
            if has('gender'):
                student.gender = form.get('gender')
            if has('date_of_birth'):
                student.date_of_birth = parse_date(form.get('date_of_birth'))
            if has('religion'):
                student.religion = form.get('religion')
            if has('home_address'):
                student.home_address = form.get('home_address', '').strip() or None
            if has('hobbies'):
                student.hobbies = form.get('hobbies', '').strip() or None
            if has('stream'):
                student.stream = form.get('stream') or None
            if has('jamb_target'):
                student.jamb_target = form.get('jamb_target', type=int)
            if complete or 'waec_subjects[]' in form:
                student.waec_subjects = ', '.join(form.getlist('waec_subjects[]')) or None
            if complete or 'jamb_subjects[]' in form:
                student.jamb_subjects = ', '.join(form.getlist('jamb_subjects[]')) or None
            _apply_optional_student_fields(student, form, has)

            # Update contacts only when the contacts section was submitted
            if not (complete or 'phone_number[]' in form):
                db.session.commit()
                log_action('student.update', detail=(_student_change_detail(before, student) or None),
                           target=student)
                flash(FlashMessages.STUDENT_UPDATED, 'success')
                dest = _safe_next(form.get('return_to'),
                                  url_for('main.view_student', student_id=student.id))
                if _wants_json():
                    return jsonify({'ok': True, 'redirect': dest})
                return redirect(dest)

            ParentContact.query.filter_by(student_id=student.id).delete()

            phone_numbers = request.form.getlist('phone_number[]')
            relationships = request.form.getlist('relationship[]')
            contact_names = request.form.getlist('contact_name[]')
            contact_emails = request.form.getlist('email[]')

            for i, phone in enumerate(phone_numbers):
                if phone.strip():
                    contact = ParentContact(
                        student_id=student.id,
                        phone_number=phone.strip(),
                        email=(contact_emails[i].strip() if i < len(contact_emails) and contact_emails[i].strip() else None),
                        relationship=relationships[i] if i < len(relationships) else 'Guardian',
                        name=contact_names[i] if i < len(contact_names) else None,
                        is_primary=(i == 0)
                    )
                    db.session.add(contact)

            db.session.commit()
            log_action('student.update', detail=(_student_change_detail(before, student) or None),
                       target=student)
            from utils.notify import notify_student_change
            notify_student_change('update', student=student,
                                  url=url_for('main.view_student', student_id=student.id))
            flash(FlashMessages.STUDENT_UPDATED, 'success')
            dest = _safe_next(request.form.get('return_to'),
                              url_for('main.view_student', student_id=student.id))
            if _wants_json():
                return jsonify({'ok': True, 'redirect': dest})
            return redirect(dest)

        except Exception as e:
            db.session.rollback()
            if _wants_json():
                return jsonify({'ok': False, 'error': f'Error updating student: {e}'}), 400
            flash(f'Error updating student: {str(e)}', 'error')

    # Remember where the user came from so we can return there after saving.
    return_to = _safe_next(
        request.form.get('return_to') or request.args.get('return_to') or request.referrer, '')
    view_url = url_for('main.view_student', student_id=student.id)
    contacts = [{'name': c.name or '', 'phone_number': c.phone_number or '',
                 'email': c.email or '', 'relationship': c.relationship or 'Father'}
                for c in student.parent_contacts.all()]
    payload = {
        'mode': 'edit',
        'student': {
            'id': student.id, 'student_id': student.student_id, 'full_name': student.full_name,
            'surname': student.surname or '', 'first_name': student.first_name or '',
            'middle_name': student.middle_name or '', 'gender': student.gender or '',
            'date_of_birth': student.date_of_birth.strftime('%Y-%m-%d') if student.date_of_birth else '',
            'religion': student.religion or '', 'stream': student.stream or '',
            'jamb_target': student.jamb_target if student.jamb_target is not None else '',
            'home_address': student.home_address or '', 'hobbies': student.hobbies or '',
            'waec_subjects': student.waec_subject_list or [],
            'jamb_subjects': student.jamb_subject_list or [],
            'house': student.house or '', 'boarding_status': student.boarding_status or '',
            'nin': student.nin or '', 'jamb_reg_number': student.jamb_reg_number or '',
            'jamb_profile_code': student.jamb_profile_code or '',
            'waec_reg_number': student.waec_reg_number or '', 'serial_number': student.serial_number or '',
            'blood_group': student.blood_group or '', 'genotype': student.genotype or '',
            'allergies': student.allergies or '', 'medical_conditions': student.medical_conditions or '',
            'disabilities': student.disabilities or '', 'medications': student.medications or '',
            'medical_notes': student.medical_notes or '', 'emergency_medical': student.emergency_medical or '',
        },
        'contacts': contacts or [_blank_contact()],
        'options': _student_form_options(),
        'return_to': return_to,
        'urls': {'submit': url_for('main.edit_student', student_id=student.id),
                 'cancel': return_to or view_url, 'back': view_url,
                 'list': url_for('main.students_list')},
    }
    return render_template('students/edit.html', form_json=payload,
                           student_name=student.full_name, student_sid=student.student_id)


@main_bp.route('/students/<int:student_id>/delete', methods=['POST'])
@login_required
def delete_student(student_id):
    """Soft-delete a student. A form teacher may delete their own class's
    students (write permission is enforced by enforce_write_level; form-class
    scope by assert_student_access) — not another class's or branch's."""
    from utils.access_control import assert_student_access
    student = db.get_or_404(Student, student_id)
    assert_student_access(student)   # no deleting another branch's/class's student by id

    try:
        student.is_active = False
        db.session.commit()
        log_action('delete_student', f'{student.full_name} ({student.student_id})')
        from utils.notify import notify_student_change
        notify_student_change('delete', detail=f'{student.full_name} ({student.student_id})')
        flash(FlashMessages.STUDENT_DELETED, 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting student: {str(e)}', 'error')

    return redirect(url_for('main.students_list'))


@main_bp.route('/students/bulk-stream', methods=['POST'])
@login_required
def bulk_set_stream():
    """Set the stream/track for several students at once (scoped to the caller's
    students — a teacher is limited to their own form class)."""
    stream = request.form.get('stream') or None
    student_ids = request.form.getlist('student_ids')

    if stream is not None and stream not in STREAMS:
        return jsonify({'error': 'Invalid stream'}), 400
    if not student_ids:
        return jsonify({'error': 'No students selected'}), 400

    try:
        ids = [int(i) for i in student_ids]
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid student ids'}), 400
    ids = _manageable_student_ids(ids)
    if not ids:
        return jsonify({'error': 'No students you can edit were selected'}), 403

    updated = Student.query.filter(Student.id.in_(ids)).update(
        {Student.stream: stream}, synchronize_session=False
    )

    # Assigning a stream should also give those students that stream's WAEC
    # subjects. Fill where the student has none yet (don't clobber a custom
    # list). Clearing the stream (stream=None) leaves WAEC subjects untouched.
    waec_filled = 0
    defaults = STREAM_WAEC_SUBJECTS.get(stream) if stream else None
    if defaults:
        joined = ', '.join(defaults)
        for student in Student.query.filter(Student.id.in_(ids)).all():
            if not student.waec_subject_list:
                student.waec_subjects = joined
                waec_filled += 1
    db.session.commit()

    label = stream if stream else 'cleared'
    log_action('bulk_set_stream', f'{updated} students -> {label}'
               + (f', WAEC filled {waec_filled}' if waec_filled else ''))
    msg = f'Stream set to {label} for {updated} student(s).'
    if waec_filled:
        msg += f' WAEC subjects filled from stream for {waec_filled}.'
    flash(msg, 'success')
    return jsonify({'updated': updated, 'stream': stream, 'waec_filled': waec_filled})


@main_bp.route('/students/bulk-gender', methods=['POST'])
@login_required
def bulk_set_gender():
    """Set the gender for several students at once (scoped to the caller's
    students — a teacher is limited to their own form class)."""
    gender = request.form.get('gender') or None
    student_ids = request.form.getlist('student_ids')

    if gender not in ('Male', 'Female'):
        return jsonify({'error': 'Invalid gender'}), 400
    if not student_ids:
        return jsonify({'error': 'No students selected'}), 400
    try:
        ids = [int(i) for i in student_ids]
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid student ids'}), 400
    ids = _manageable_student_ids(ids)
    if not ids:
        return jsonify({'error': 'No students you can edit were selected'}), 403

    updated = Student.query.filter(Student.id.in_(ids)).update(
        {Student.gender: gender}, synchronize_session=False
    )
    db.session.commit()
    log_action('bulk_set_gender', f'{updated} students -> {gender}')
    flash(f'Gender set to {gender} for {updated} student(s).', 'success')
    return jsonify({'updated': updated, 'gender': gender})


@main_bp.route('/students/bulk-house', methods=['POST'])
@login_required
def bulk_set_house():
    """Assign a pastoral house to several students at once (scoped to the
    caller's students). Blank clears the house."""
    house = (request.form.get('house') or '').strip()
    house = strip_tags(house)[:40] or None
    student_ids = request.form.getlist('student_ids')
    if not student_ids:
        return jsonify({'error': 'No students selected'}), 400
    try:
        ids = [int(i) for i in student_ids]
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid student ids'}), 400
    ids = _manageable_student_ids(ids)
    if not ids:
        return jsonify({'error': 'No students you can edit were selected'}), 403
    updated = Student.query.filter(Student.id.in_(ids)).update(
        {Student.house: house}, synchronize_session=False)
    db.session.commit()
    label = house if house else 'cleared'
    log_action('bulk_set_house', f'{updated} students -> {label}')
    flash(f'House set to {label} for {updated} student(s).', 'success')
    return jsonify({'updated': updated, 'house': house})


@main_bp.route('/students/bulk-boarding', methods=['POST'])
@login_required
def bulk_set_boarding():
    """Set boarding status (Day/Boarding) for several students at once."""
    boarding = request.form.get('boarding') or None
    if boarding not in ('Day', 'Boarding'):
        return jsonify({'error': 'Invalid boarding status'}), 400
    student_ids = request.form.getlist('student_ids')
    if not student_ids:
        return jsonify({'error': 'No students selected'}), 400
    try:
        ids = [int(i) for i in student_ids]
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid student ids'}), 400
    ids = _manageable_student_ids(ids)
    if not ids:
        return jsonify({'error': 'No students you can edit were selected'}), 403
    updated = Student.query.filter(Student.id.in_(ids)).update(
        {Student.boarding_status: boarding}, synchronize_session=False)
    db.session.commit()
    log_action('bulk_set_boarding', f'{updated} students -> {boarding}')
    flash(f'Boarding status set to {boarding} for {updated} student(s).', 'success')
    return jsonify({'updated': updated, 'boarding': boarding})


@main_bp.route('/students/bulk-message', methods=['POST'])
@login_required
def bulk_message_students():
    """Draft a Communication campaign to the selected students' parents. Reuses
    the shared campaign builder (never auto-sends on a gateway channel) and hands
    the user to Communication to review + send. Scoped to the caller's students."""
    body = (request.form.get('body') or '').strip()
    channel = request.form.get('channel') or 'SMS'
    title = strip_tags(request.form.get('title') or '')[:120] or None
    student_ids = request.form.getlist('student_ids')
    if not body:
        return jsonify({'error': 'Message body is required'}), 400
    if not student_ids:
        return jsonify({'error': 'No students selected'}), 400
    try:
        ids = [int(i) for i in student_ids]
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid student ids'}), 400
    ids = _manageable_student_ids(ids)
    if not ids:
        return jsonify({'error': 'No students you can message were selected'}), 403

    from utils import comms
    from utils.access_control import get_current_user
    who = getattr(get_current_user(), 'full_name', None) or 'Staff'
    msg = comms.build_campaign(
        body, channel=channel, term=get_active_term(),
        title=title or 'Message to parents',
        spec={'to': 'parents', 'audience': 'students', 'student_ids': ids},
        created_by=who)
    if not msg:
        return jsonify({'error': 'None of those students have a reachable parent '
                        f'contact for {channel}.'}), 400
    log_action('bulk_message_students',
               f'draft to parents of {len(ids)} students -> message {msg.id}')
    review_url = url_for('comms.message_detail', message_id=msg.id)
    return jsonify({'ok': True, 'message_id': msg.id, 'recipients': msg.recipient_count,
                    'students': len(ids), 'review_url': review_url,
                    'info': f'Drafted a {channel} message for {msg.recipient_count} '
                            'parent(s) — review and send in Communication.'})


@main_bp.route('/students/bulk-add-subject', methods=['POST'])
@admin_required
def bulk_add_subject():
    """Add a WAEC subject to selected students' enrolled subjects (SSS3 only)."""
    subject = (request.form.get('subject') or '').strip()
    student_ids = request.form.getlist('student_ids')
    if subject not in WAEC_SUBJECTS:
        return jsonify({'error': 'Invalid subject'}), 400
    if not student_ids:
        return jsonify({'error': 'No students selected'}), 400
    try:
        ids = [int(i) for i in student_ids]
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid student ids'}), 400

    # Which of the selected students are SSS3 (current/active term)?
    active_term = get_active_term()
    sss3_q = (db.session.query(StudentEnrollment.student_id)
              .join(ClassArmAssignment,
                    StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
              .join(SchoolClass, ClassArmAssignment.class_id == SchoolClass.id)
              .filter(StudentEnrollment.is_active == True,
                      SchoolClass.name == 'SSS3',
                      StudentEnrollment.student_id.in_(ids)))
    if active_term:
        sss3_q = sss3_q.filter(ClassArmAssignment.term_id == active_term.id)
    sss3_ids = {r[0] for r in sss3_q.all()}

    updated = skipped = 0
    for student in Student.query.filter(Student.id.in_(ids)).all():
        if student.id not in sss3_ids:
            skipped += 1
            continue
        subs = student.waec_subject_list
        if subject in subs:
            skipped += 1
            continue
        subs.append(subject)
        student.waec_subjects = ', '.join(subs)
        updated += 1
    db.session.commit()
    log_action('bulk_add_subject', f'{subject} -> {updated} SSS3 students')
    flash(f'Added "{subject}" to {updated} SSS3 student(s).', 'success')
    return jsonify({'updated': updated, 'skipped': skipped, 'subject': subject})


@main_bp.route('/students/apply-stream-waec', methods=['POST'])
@admin_required
def apply_stream_waec():
    """Fill WAEC subjects from each student's stream where not already set."""
    updated = 0
    for student in Student.query.filter_by(is_active=True).all():
        defaults = STREAM_WAEC_SUBJECTS.get(student.stream)
        if defaults and not student.waec_subject_list:
            student.waec_subjects = ', '.join(defaults)
            updated += 1
    db.session.commit()
    flash(f'WAEC subjects filled from stream for {updated} student(s).', 'success')
    return safe_redirect(url_for('main.students_list'))


@main_bp.route('/students/bulk-delete', methods=['POST'])
@admin_required
def bulk_delete_students():
    """Soft-delete several students at once (sends them to the trash)."""
    student_ids = request.form.getlist('student_ids')
    if not student_ids:
        return jsonify({'error': 'No students selected'}), 400
    try:
        ids = [int(i) for i in student_ids]
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid student ids'}), 400

    deleted = Student.query.filter(
        Student.id.in_(ids), Student.is_active == True
    ).update({Student.is_active: False}, synchronize_session=False)
    db.session.commit()
    log_action('bulk_delete_students', f'{deleted} students soft-deleted')
    return jsonify({'deleted': deleted})


@main_bp.route('/students/trash')
@login_required
def students_trash():
    """List soft-deleted students with restore / permanent-delete options."""
    return render_template('students/trash.html', trash_json=_trash_payload())


@main_bp.route('/students/<int:student_id>/restore', methods=['POST'])
@login_required
def restore_student(student_id):
    from utils.access_control import assert_student_access
    student = db.get_or_404(Student, student_id)
    assert_student_access(student)   # branch + form-teacher scope
    student.is_active = True
    db.session.commit()
    log_action('restore_student', f'{student.full_name} ({student.student_id})')
    if _wants_json():
        return jsonify({'ok': True})
    flash(f'{student.full_name} restored.', 'success')
    return redirect(url_for('main.students_trash'))


@main_bp.route('/students/<int:student_id>/purge', methods=['POST'])
@login_required
def purge_student(student_id):
    """Permanently delete a soft-deleted student and their related records."""
    from utils.access_control import assert_student_access
    student = db.get_or_404(Student, student_id)
    assert_student_access(student)   # branch + form-teacher scope
    if student.is_active:
        if _wants_json():
            return jsonify({'ok': False, 'error': 'Only deleted students can be permanently removed.'}), 400
        flash('Only deleted students can be permanently removed.', 'error')
        return redirect(url_for('main.students_trash'))
    name = student.full_name
    sid = student.student_id
    try:
        db.session.delete(student)
        db.session.commit()
        log_action('purge_student', f'{name} ({sid})')
        if _wants_json():
            return jsonify({'ok': True})
        flash(f'{name} permanently deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        if _wants_json():
            return jsonify({'ok': False, 'error': str(e)}), 400
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('main.students_trash'))


@main_bp.route('/students/bulk-restore', methods=['POST'])
@login_required
def bulk_restore_students():
    """Restore several soft-deleted students at once (branch + teacher scoped)."""
    ids = _int_ids(request.form.getlist('student_ids'))
    if not ids:
        return _bulk_no_selection()
    restored = _trash_scope(
        Student.query.filter(Student.id.in_(ids), Student.is_active == False)
    ).update({Student.is_active: True}, synchronize_session=False)
    db.session.commit()
    log_action('bulk_restore_students', f'{restored} students restored')
    if _wants_json():
        return jsonify({'ok': True, 'restored': restored})
    flash(f'{restored} student(s) restored.', 'success')
    return redirect(url_for('main.students_trash'))


@main_bp.route('/students/bulk-purge', methods=['POST'])
@login_required
def bulk_purge_students():
    """Permanently delete several soft-deleted students at once (branch + teacher scoped)."""
    ids = _int_ids(request.form.getlist('student_ids'))
    if not ids:
        return _bulk_no_selection()
    students = _trash_scope(
        Student.query.filter(Student.id.in_(ids), Student.is_active == False)
    ).all()
    purged = 0
    try:
        for student in students:
            db.session.delete(student)
            purged += 1
        db.session.commit()
        log_action('bulk_purge_students', f'{purged} students permanently deleted')
        if _wants_json():
            return jsonify({'ok': True, 'purged': purged})
        flash(f'{purged} student(s) permanently deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        if _wants_json():
            return jsonify({'ok': False, 'error': str(e)}), 400
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('main.students_trash'))


@main_bp.route('/api/students/search')
@login_required
def api_search_students():
    """API endpoint for student search (AJAX)"""
    query = request.args.get('q', '')

    if len(query) < 2:
        return jsonify([])

    students = _viewer_student_scope(Student.query.filter(Student.is_active == True)).filter(
        db.or_(
            Student.first_name.ilike(like_term(query), escape='\\'),
            Student.surname.ilike(like_term(query), escape='\\'),
            Student.student_id.ilike(like_term(query), escape='\\')
        )
    ).limit(10).all()

    return jsonify([{
        'id': s.id,
        'student_id': s.student_id,
        'name': s.full_name,
        'gender': s.gender
    } for s in students])


@main_bp.route('/students/export')
@login_required
def export_students_data():
    """Export selected students data to various formats with field selection"""
    import json
    
    format_type = request.args.get('format', 'excel')
    fields_json = request.args.get('fields', '[]')
    student_ids_json = request.args.get('student_ids', '[]')
    
    try:
        fields = json.loads(fields_json)
        student_ids = json.loads(student_ids_json)
    except Exception:
        fields = ['student_id', 'surname', 'first_name', 'gender', 'current_class']
        student_ids = []
    
    if not fields:
        flash('No fields selected for export.', 'error')
        return redirect(url_for('main.students_list'))
    
    # Build query
    if student_ids:
        # Export selected students (scoped: a teacher can't export other classes)
        query = _viewer_student_scope(Student.query.filter(Student.id.in_(student_ids)))
    else:
        # Export all students matching current filters
        query = _viewer_student_scope(Student.query.filter_by(is_active=True))
        
        # Apply filters
        search = request.args.get('search', '')
        gender = request.args.get('gender', '')
        religion = request.args.get('religion', '')
        class_id = request.args.get('class_id', type=int)
        arm_id = request.args.get('arm_id', type=int)
        
        if search:
            search_term = like_term(search)
            query = query.filter(
                db.or_(
                    Student.first_name.ilike(search_term, escape='\\'),
                    Student.surname.ilike(search_term, escape='\\'),
                    Student.middle_name.ilike(search_term, escape='\\'),
                    Student.student_id.ilike(search_term, escape='\\')
                )
            )
        if gender:
            query = query.filter(Student.gender == gender)
        if religion:
            query = query.filter(Student.religion == religion)
        
        if class_id or arm_id:
            active_term = get_active_term()
            if active_term:
                query = query.join(
                    StudentEnrollment, Student.id == StudentEnrollment.student_id
                ).join(
                    ClassArmAssignment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id
                ).filter(ClassArmAssignment.term_id == active_term.id)
                
                if class_id:
                    query = query.filter(ClassArmAssignment.class_id == class_id)
                if arm_id:
                    query = query.filter(ClassArmAssignment.arm_id == arm_id)
    
    students = query.order_by(Student.surname).all()
    
    if not students:
        flash('No students to export.', 'error')
        return redirect(url_for('main.students_list'))
    
    # Pre-load current class + parent phone for every student in two queries
    # (instead of two per student) to avoid N+1 during export.
    active_term = get_active_term()
    student_ids = [s.id for s in students]

    class_map = {}
    if active_term:
        enr = (StudentEnrollment.query
               .join(ClassArmAssignment)
               .filter(StudentEnrollment.student_id.in_(student_ids),
                       ClassArmAssignment.term_id == active_term.id)
               .options(joinedload(StudentEnrollment.class_arm_assignment)
                        .joinedload(ClassArmAssignment.school_class),
                        joinedload(StudentEnrollment.class_arm_assignment)
                        .joinedload(ClassArmAssignment.arm))
               .all())
        for e in enr:
            class_map[e.student_id] = e.class_arm_assignment.display_name

    phone_map = {}
    for pc in (ParentContact.query
               .filter(ParentContact.student_id.in_(student_ids))
               .order_by(ParentContact.is_primary.desc(), ParentContact.id).all()):
        phone_map.setdefault(pc.student_id, pc.phone_number)

    student_data = []

    for student in students:
        data = {}
        
        # Basic fields
        if 'student_id' in fields:
            data['Student ID'] = student.student_id
        if 'surname' in fields:
            data['Surname'] = student.surname
        if 'first_name' in fields:
            data['First Name'] = student.first_name
        if 'middle_name' in fields:
            data['Middle Name'] = student.middle_name or ''
        if 'gender' in fields:
            data['Gender'] = student.gender
        if 'date_of_birth' in fields:
            data['Date of Birth'] = student.date_of_birth.strftime('%Y-%m-%d') if student.date_of_birth else ''
        if 'age' in fields:
            data['Age'] = student.age or ''
        if 'religion' in fields:
            data['Religion'] = student.religion or ''
        if 'home_address' in fields:
            data['Home Address'] = student.home_address or ''
        if 'hobbies' in fields:
            data['Hobbies'] = student.hobbies or ''
        
        # Current class
        if 'current_class' in fields:
            data['Class'] = class_map.get(student.id, '')

        # Parent phone
        if 'parent_phone' in fields:
            data['Parent Phone'] = phone_map.get(student.id, '')
        
        student_data.append(data)
    
    # Get ordered field names for export
    field_order = ['Student ID', 'Surname', 'First Name', 'Middle Name', 'Gender', 
                   'Class', 'Date of Birth', 'Age', 'Religion', 'Home Address', 
                   'Hobbies', 'Parent Phone']
    export_fields = [f for f in field_order if f in student_data[0]] if student_data else []
    
    if format_type == 'excel':
        return export_students_excel(student_data, export_fields)
    elif format_type == 'word':
        return export_students_word(student_data, export_fields)
    elif format_type == 'pdf':
        return export_students_pdf(student_data, export_fields)
    elif format_type == 'image':
        return export_students_image(student_data, export_fields)
    else:
        flash('Invalid export format.', 'error')
        return redirect(url_for('main.students_list'))
