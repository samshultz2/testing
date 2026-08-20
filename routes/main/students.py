"""main blueprint — students routes (split from the former routes/main.py)."""
from routes.main import *  # noqa: F401,F403  (blueprint, models, helpers)
from utils.search import like_term
from utils.security import strip_tags


def _sp_has_photo(student):
    try:
        from utils.student_photo import has_photo
        return has_photo(student)
    except Exception:
        return False


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
    'waec_epin': 'WAEC e-PIN',
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


# --- University-aspiration reference lookups (searchable dropdowns + auto-fill) --
@main_bp.route('/api/universities')
@login_required
def api_universities():
    """Searchable university list for the aspiration dropdown."""
    from models import University
    q = (request.args.get('q') or '').strip()
    query = University.query.filter_by(is_active=True)
    if q:
        like = like_term(q)
        query = query.filter(db.or_(University.name.ilike(like, escape='\\'),
                                    University.abbreviation.ilike(like, escape='\\')))
    rows = query.order_by(University.name).limit(50).all()
    return jsonify({'universities': [u.as_dict() for u in rows]})


@main_bp.route('/api/courses')
@login_required
def api_courses():
    """Searchable course list for the aspiration dropdown."""
    from models import Course
    q = (request.args.get('q') or '').strip()
    query = Course.query.filter_by(is_active=True)
    if q:
        like = like_term(q)
        query = query.filter(db.or_(Course.name.ilike(like, escape='\\'),
                                    Course.department.ilike(like, escape='\\')))
    rows = query.order_by(Course.name).limit(50).all()
    return jsonify({'courses': [c.as_dict() for c in rows]})


@main_bp.route('/api/course-requirements')
@login_required
def api_course_requirements():
    """For a chosen course (+ optional university), the department, competitive
    JAMB target and the JAMB/WAEC subject requirements — drives the form auto-fill."""
    from models import Course, University, effective_cutoff
    course = db.session.get(Course, request.args.get('course_id', type=int))
    if not course:
        return jsonify({'error': 'unknown course'}), 404
    university = db.session.get(University, request.args.get('university_id', type=int))
    return jsonify({
        'department': course.department or '',
        'jamb_target': effective_cutoff(university, course),
        'jamb_subjects': course.jamb_subject_list,
        'waec_subjects': course.waec_subject_list,
    })


@main_bp.route('/api/students/<int:student_id>/recommend-courses')
@login_required
def api_recommend_courses(student_id):
    """Courses the student is projected to be competitive for (at their target
    university, or a given ?university_id). Scoped like viewing the student."""
    from models import University
    from utils.aspiration import recommend_courses
    student, err = _student_or_redirect(student_id)
    if err:
        return jsonify({'error': 'forbidden'}), 403
    uid = request.args.get('university_id', type=int)
    uni = db.session.get(University, uid) if uid else None
    return jsonify({'recommendations': recommend_courses(student, university=uni)})


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
        # Soft plan cap: block only the create when a tiered tenant is over its
        # student limit (never affects payments, existing students or reads).
        from utils.entitlements import cap_block
        capped = cap_block('students', 'main.students_list', 'students')
        if capped is not None:
            if _wants_json():
                return jsonify({'ok': False, 'error': "You've reached your plan's "
                                "student limit. Upgrade your subscription to add more."}), 402
            return capped
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
            _apply_aspiration_fields(student, request.form)

            db.session.add(student)
            db.session.flush()
            _apply_scholarships(student, request.form)

            # Optional passport photo (data: URL from the form). A bad image must
            # never block saving the student, so failures are swallowed.
            try:
                from utils import student_photo as _sp
                _sp.apply_from_form(student, request.form.get('photo'))
            except Exception:
                pass

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
            from utils import query_cache
            query_cache.bump('dash')          # student count/recent changed
            log_action('student.create', target=student)
            view_url = url_for('main.view_student', student_id=student.id)
            from utils.notify import notify_student_change, actor_label
            notify_student_change('create', student=student, actor=actor_label(), url=view_url)
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
    # Soft plan cap: bulk import is the easiest way past a limit, so block a
    # commit that would push a tiered tenant over its student cap. Headroom-aware
    # (not just "already over") since one paste can add many rows. Payments and
    # existing students are never affected.
    from utils.entitlements import creation_cap_check
    _cap = creation_cap_check('students')
    if _cap:
        incoming = prev.get('valid') or 0
        remaining = max(0, _cap['cap'] - _cap['used'])
        if _cap['over'] or incoming > remaining:
            return jsonify({'ok': False, 'error':
                f"This import would exceed your {_cap['tier_label']} plan limit of "
                f"{_cap['cap']} students — you have {_cap['used']} and {remaining} "
                f"slot(s) left. Existing students and payments are unaffected; "
                f"upgrade your subscription to import more, or trim the list."}), 402

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
        from utils import query_cache
        query_cache.bump('dash')          # student count changed
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


@main_bp.route('/students/<int:student_id>/photo')
@login_required
def student_photo(student_id):
    """Serve a student's passport photo from the tenant DB — behind login + branch
    scope (it is PII), never public. Cached privately + ETag'd."""
    from flask import Response
    from models import StudentPhoto
    student, err = _student_or_redirect(student_id)
    if err:
        abort(404)
    row = StudentPhoto.query.filter_by(student_id=student.id).first()
    if row is None or not row.data:
        abort(404)
    etag = 'sp-%d-%d' % (row.id, row.bytes or 0)
    if request.headers.get('If-None-Match') == etag:
        return Response(status=304)
    resp = Response(bytes(row.data), mimetype=row.mime or 'image/jpeg')
    resp.headers['Cache-Control'] = 'private, max-age=3600'
    resp.headers['ETag'] = etag
    return resp


def _id_card_fields(student):
    """Resolve the display fields an ID card needs for one student: current
    class/arm + session (most recent enrolment), primary guardian, DOB, address
    and the public verification URL. Kept query-light so a whole class can be
    rendered in one route."""
    class_label, session_name = '', ''
    enr = (student.enrollments.join(ClassArmAssignment)
           .order_by(ClassArmAssignment.term_id.desc()).first())
    if enr and enr.class_arm_assignment:
        caa = enr.class_arm_assignment
        try:
            class_label = caa.display_name
        except Exception:
            class_label = ''
        try:
            session_name = caa.term.session.name
        except Exception:
            session_name = ''
    guardian, guardian_phone = '', ''
    gc = (student.parent_contacts.filter_by(is_primary=True).first()
          or student.parent_contacts.first())
    if gc:
        guardian = gc.name or gc.relationship or ''
        guardian_phone = gc.phone_number or ''
    dob = student.date_of_birth.strftime('%d %b %Y') if student.date_of_birth else ''
    return {
        'student': student, 'class_label': class_label, 'session': session_name,
        'dob': dob, 'guardian': guardian, 'guardian_phone': guardian_phone,
        'address': student.home_address or '', 'verify': None,
    }


@main_bp.route('/students/<int:student_id>/id-card')
@login_required
def student_id_card(student_id):
    """Download a printable student ID card (front + back on one A4 sheet)."""
    from flask import send_file
    from utils import id_card
    from utils.school import school_profile, document_branding
    student, err = _student_or_redirect(student_id)
    if err:
        flash(err[1], 'error')
        return redirect(url_for('main.students_list'))
    try:
        branding = document_branding()
    except Exception:
        branding = {}
    f = _id_card_fields(student)
    buf = id_card.render_id_card(
        student, school=school_profile(), class_label=f['class_label'],
        session=f['session'], dob=f['dob'], guardian=f['guardian'],
        guardian_phone=f['guardian_phone'], address=f['address'], branding=branding)
    log_action('student_id_card', student.full_name)
    return send_file(buf, mimetype='application/pdf', as_attachment=True,
                     download_name=f"id_card_{student.student_id or student.id}.pdf")


@main_bp.route('/students/id-cards', methods=['POST'])
@login_required
def bulk_id_cards():
    """Download a whole selection's ID cards as one printable PDF (6 cards per A4
    page — fronts, then backs in the same order). Scoped to the caller's
    students, like every other bulk action."""
    from flask import send_file
    from utils import id_card
    from utils.school import school_profile, document_branding
    ids = _int_ids(request.form.getlist('student_ids'))
    if not ids:
        return _bulk_no_selection()
    ids = _manageable_student_ids(ids)
    if not ids:
        return jsonify({'error': 'No students you can print were selected'}), 403
    order = {sid: i for i, sid in enumerate(ids)}
    students = sorted(Student.query.filter(Student.id.in_(ids)).all(),
                      key=lambda s: order.get(s.id, 0))
    include_backs = request.form.get('backs', '1') != '0'
    try:
        branding = document_branding()
    except Exception:
        branding = {}
    cards = [_id_card_fields(s) for s in students]
    buf = id_card.render_class_id_cards(
        cards, school=school_profile(), branding=branding,
        include_backs=include_backs)
    log_action('bulk_id_cards', f'{len(cards)} ID card(s)')
    return send_file(buf, mimetype='application/pdf', as_attachment=True,
                     download_name=f"id_cards_{len(cards)}.pdf")


_PHOTO_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp')


def _norm_key(s):
    """Normalise a token for matching: drop spaces and the common separators used
    in admission numbers, and lower-case, so ``ADM/2024/001`` and ``adm-2024-001``
    compare equal."""
    return (''.join((s or '').split())
            .replace('-', '').replace('/', '').replace('\\', '').replace('_', '')
            .lower())


def _file_key(name):
    """Match key for a photo file: its base name (directory dropped) without the
    extension, normalised. A zip entry like ``class/ADM-2024-001.jpg`` keys to
    ``adm2024001``."""
    import os
    base = os.path.basename((name or '').replace('\\', '/'))
    return _norm_key(os.path.splitext(base)[0])


@main_bp.route('/students/import-photos', methods=['POST'])
@login_required
def import_photos():
    """Bulk-import passport photos from an uploaded .zip, matching each image to a
    student by admission number (the file's base name, e.g. ``STU-001.jpg``).
    Branch-scoped: only the caller's students are touched. Returns a JSON summary
    of matched / skipped / unmatched files."""
    import io as _io
    import zipfile
    from utils.branch_scope import scope_query
    from utils.access_control import teacher_form_student_ids
    from utils import student_photo as _sp

    up = request.files.get('archive') or request.files.get('file')
    if up is None or not (up.filename or '').lower().endswith('.zip'):
        return jsonify({'error': 'Upload a .zip of photos named by admission number.'}), 400
    raw = up.read()
    if len(raw) > 60 * 1024 * 1024:
        return jsonify({'error': 'That archive is too large (max 60 MB).'}), 400
    try:
        zf = zipfile.ZipFile(_io.BytesIO(raw))
    except Exception:
        return jsonify({'error': 'That file is not a valid .zip archive.'}), 400

    # Build the match index over the caller's scoped students only.
    q = scope_query(Student.query.filter_by(is_active=True), Student)
    tids = teacher_form_student_ids()
    if tids is not None:
        q = q.filter(Student.id.in_(tids or {-1}))
    by_key = {}
    for s in q.all():
        if s.student_id:
            by_key.setdefault(_norm_key(s.student_id), s)

    matched, skipped, unmatched, errors = 0, 0, [], []
    seen = set()
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = info.filename
        low = name.lower()
        if not low.endswith(_PHOTO_EXTS) or '__macosx' in low:
            continue
        if info.file_size > _sp.MAX_INPUT_BYTES:
            errors.append(f'{name}: too large'); continue
        key = _file_key(name)
        student = by_key.get(key)
        if student is None:
            unmatched.append(name); continue
        if student.id in seen:
            skipped += 1; continue          # first image per student wins
        try:
            _sp.save_bytes(student, zf.read(info))
            seen.add(student.id); matched += 1
        except Exception as exc:
            errors.append(f'{name}: {exc}')
    if matched:
        db.session.commit()
    else:
        db.session.rollback()
    log_action('import_photos', f'{matched} matched, {len(unmatched)} unmatched')
    msg = f'{matched} photo(s) imported.'
    if unmatched:
        msg += f' {len(unmatched)} file(s) matched no admission number.'
    flash(msg, 'success' if matched else 'error')
    return jsonify({'ok': True, 'matched': matched, 'skipped': skipped,
                    'unmatched': unmatched[:50], 'unmatched_count': len(unmatched),
                    'errors': errors[:20], 'message': msg})


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
            _apply_aspiration_fields(student, form, has)
            _apply_scholarships(student, form)

            # Passport photo: data: URL replaces it, '' removes it; absent leaves
            # it untouched (so a partial POST never wipes it). Never blocks a save.
            if has('photo'):
                try:
                    from utils import student_photo as _sp
                    _sp.apply_from_form(student, form.get('photo'))
                except Exception:
                    pass

            # Update contacts only when the contacts section was submitted
            if not (complete or 'phone_number[]' in form):
                db.session.commit()
                _changes = _student_change_detail(before, student)
                log_action('student.update', detail=(_changes or None), target=student)
                from utils.notify import notify_student_change, actor_label
                notify_student_change('update', student=student, changes=_changes,
                                      actor=actor_label(),
                                      url=url_for('main.view_student', student_id=student.id))
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
            _changes = _student_change_detail(before, student)
            log_action('student.update', detail=(_changes or None), target=student)
            from utils.notify import notify_student_change, actor_label
            notify_student_change('update', student=student, changes=_changes,
                                  actor=actor_label(),
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
            'photo_url': (url_for('main.student_photo', student_id=student.id)
                          if _sp_has_photo(student) else ''),
            'waec_subjects': student.waec_subject_list or [],
            'jamb_subjects': student.jamb_subject_list or [],
            'house': student.house or '', 'boarding_status': student.boarding_status or '',
            'nin': student.nin or '', 'jamb_reg_number': student.jamb_reg_number or '',
            'jamb_profile_code': student.jamb_profile_code or '',
            'waec_reg_number': student.waec_reg_number or '', 'serial_number': student.serial_number or '',
            'waec_epin': student.waec_epin or '',
            'blood_group': student.blood_group or '', 'genotype': student.genotype or '',
            'allergies': student.allergies or '', 'medical_conditions': student.medical_conditions or '',
            'disabilities': student.disabilities or '', 'medications': student.medications or '',
            'medical_notes': student.medical_notes or '', 'emergency_medical': student.emergency_medical or '',
            'target_university_id': student.target_university_id or '',
            'target_course_id': student.target_course_id or '',
            'target_department': student.target_department or '',
            'target_university_label': (student.target_university.as_dict()['label']
                                        if student.target_university else ''),
            'target_course_label': (student.target_course.name if student.target_course else ''),
            'target2_university_id': student.target2_university_id or '',
            'target2_course_id': student.target2_course_id or '',
            'target2_university_label': (student.target2_university.as_dict()['label']
                                         if student.target2_university else ''),
            'target2_course_label': (student.target2_course.name if student.target2_course else ''),
            'career_goal': student.career_goal or '',
            'admission_status': student.admission_status or '',
            'admitted_university_id': student.admitted_university_id or '',
            'admitted_course_id': student.admitted_course_id or '',
            'admitted_university_label': (student.admitted_university.as_dict()['label']
                                          if student.admitted_university else ''),
            'admitted_course_label': (student.admitted_course.name if student.admitted_course else ''),
            'scholarships': [sc.as_dict() for sc in student.scholarships.all()],
        },
        'contacts': contacts or [_blank_contact()],
        'options': _student_form_options(),
        'return_to': return_to,
        'urls': {'submit': url_for('main.edit_student', student_id=student.id),
                 'cancel': return_to or view_url, 'back': view_url,
                 'list': url_for('main.students_list'),
                 'recommend': url_for('main.api_recommend_courses', student_id=student.id)},
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
        from utils import query_cache
        query_cache.bump('dash')          # active student count changed
        log_action('delete_student', f'{student.full_name} ({student.student_id})')
        from utils.notify import notify_student_change, actor_label
        notify_student_change('delete', detail=f'{student.full_name} ({student.student_id})',
                              actor=actor_label())
        flash(FlashMessages.STUDENT_DELETED, 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting student: {str(e)}', 'error')

    return redirect(url_for('main.students_list'))


@main_bp.route('/students/bulk-aspiration', methods=['POST'])
@login_required
def bulk_set_aspiration():
    """Assign the same university and/or course aspiration to several students at
    once (scoped to the caller's students). Setting a course auto-fills each
    student's JAMB target (the course's competitive cut-off for the chosen
    university) and their JAMB subject requirements where empty. WAEC subjects are
    left untouched."""
    from models import University, Course, effective_cutoff
    ids = _manageable_student_ids(_int_ids(request.form.getlist('student_ids')))
    if not ids:
        return jsonify({'error': 'No students you can edit were selected'}), 403
    university = db.session.get(University, request.form.get('target_university_id', type=int))
    course = db.session.get(Course, request.form.get('target_course_id', type=int))
    if not (university or course):
        return jsonify({'error': 'Choose a university and/or a course to assign'}), 400

    students = Student.query.filter(Student.id.in_(ids)).all()
    for s in students:
        if university is not None:
            s.target_university_id = university.id
        if course is not None:
            s.target_course_id = course.id
            s.target_department = course.department or s.target_department
        eff_course = course or s.target_course
        eff_uni = university or s.target_university
        if eff_course is not None:
            s.jamb_target = effective_cutoff(eff_uni, eff_course)
            if course is not None:      # only fill JAMB subjects when a course was chosen
                if not s.jamb_subject_list and eff_course.jamb_subjects:
                    s.jamb_subjects = eff_course.jamb_subjects
                # WAEC subjects are intentionally left as-is.
    db.session.commit()

    bits = []
    if university is not None:
        bits.append(university.name)
    if course is not None:
        bits.append(course.name)
    log_action('bulk_set_aspiration', f'{len(students)} students -> {" · ".join(bits)}')
    msg = f'Aspiration set for {len(students)} student(s): {" · ".join(bits)}.'
    if _wants_json():
        return jsonify({'ok': True, 'message': msg, 'updated': len(students)})
    flash(msg, 'success')
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

    # Assigning a stream should also give those students that stream's WAEC and
    # JAMB subjects (from the per-school config). Fill where the student has none
    # yet (don't clobber a custom list). Clearing the stream (stream=None) leaves
    # the subject lists untouched.
    from utils.exam_subject_config import stream_waec_subjects, stream_jamb_subjects
    waec_filled = jamb_filled = 0
    waec_defaults = stream_waec_subjects(stream) if stream else []
    jamb_defaults = stream_jamb_subjects(stream) if stream else []
    if waec_defaults or jamb_defaults:
        waec_joined = ', '.join(waec_defaults)
        jamb_joined = ', '.join(jamb_defaults)
        for student in Student.query.filter(Student.id.in_(ids)).all():
            if waec_defaults and not student.waec_subject_list:
                student.waec_subjects = waec_joined
                waec_filled += 1
            if jamb_defaults and not student.jamb_subject_list:
                student.jamb_subjects = jamb_joined
                jamb_filled += 1
    db.session.commit()

    label = stream if stream else 'cleared'
    fills = []
    if waec_filled:
        fills.append(f'WAEC filled {waec_filled}')
    if jamb_filled:
        fills.append(f'JAMB filled {jamb_filled}')
    log_action('bulk_set_stream', f'{updated} students -> {label}'
               + (f', {", ".join(fills)}' if fills else ''))
    msg = f'Stream set to {label} for {updated} student(s).'
    if waec_filled:
        msg += f' WAEC subjects filled for {waec_filled}.'
    if jamb_filled:
        msg += f' JAMB subjects filled for {jamb_filled}.'
    flash(msg, 'success')
    return jsonify({'updated': updated, 'stream': stream,
                    'waec_filled': waec_filled, 'jamb_filled': jamb_filled})


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
    from utils.exam_subject_config import stream_waec_subjects
    updated = 0
    for student in Student.query.filter_by(is_active=True).all():
        defaults = stream_waec_subjects(student.stream)
        if defaults and not student.waec_subject_list:
            student.waec_subjects = ', '.join(defaults)
            updated += 1
    db.session.commit()
    flash(f'WAEC subjects filled from stream for {updated} student(s).', 'success')
    return safe_redirect(url_for('main.students_list'))


@main_bp.route('/students/apply-stream-subjects', methods=['POST'])
@admin_required
def apply_stream_subjects():
    """Extrapolate a stream's compulsory WAEC + JAMB subjects to every SSS2/SSS3
    student in that stream. Fills empties only (never clobbers a custom list).
    Triggered by the explicit button on the student edit page."""
    import re
    from utils.exam_subject_config import stream_waec_subjects, stream_jamb_subjects
    from utils.branch_scope import scope_query
    stream = (request.form.get('stream') or '').strip()
    if stream not in STREAMS:
        return jsonify({'error': 'Choose a valid stream first.'}), 400

    waec_defaults = stream_waec_subjects(stream)
    jamb_defaults = stream_jamb_subjects(stream)

    # Senior classes that carry streams (SSS2 + SSS3), matched tolerantly.
    senior_ids = []
    for c in SchoolClass.query.all():
        norm = re.sub(r'[^a-z0-9]', '', (c.name or '').lower())
        if norm in ('sss2', 'ss2', 'seniorsecondary2', 'sss3', 'ss3', 'seniorsecondary3'):
            senior_ids.append(c.id)

    active_term = get_active_term()
    students = {}
    if senior_ids and active_term:
        assignments = scope_query(ClassArmAssignment.query.filter(
            ClassArmAssignment.class_id.in_(senior_ids),
            ClassArmAssignment.term_id == active_term.id), ClassArmAssignment).all()
        for a in assignments:
            for e in StudentEnrollment.query.filter_by(
                    class_arm_assignment_id=a.id, is_active=True).join(Student).all():
                st = e.student
                if st.is_active and st.stream == stream:
                    students[st.id] = st

    waec_joined = ', '.join(waec_defaults)
    jamb_joined = ', '.join(jamb_defaults)
    waec_filled = jamb_filled = 0
    for st in students.values():
        if waec_defaults and not st.waec_subject_list:
            st.waec_subjects = waec_joined
            waec_filled += 1
        if jamb_defaults and not st.jamb_subject_list:
            st.jamb_subjects = jamb_joined
            jamb_filled += 1
    db.session.commit()
    log_action('apply_stream_subjects',
               f'{stream}: WAEC filled {waec_filled}, JAMB filled {jamb_filled} '
               f'(of {len(students)} SSS2/SSS3 students)')
    return jsonify({'stream': stream, 'matched': len(students),
                    'waec_filled': waec_filled, 'jamb_filled': jamb_filled})


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
    from utils import query_cache
    query_cache.bump('dash')              # active student count changed
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
    from utils import query_cache
    query_cache.bump('dash')              # active student count changed
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

        # External-exam identity records
        if 'nin' in fields:
            data['NIN'] = student.nin or ''
        if 'jamb_profile_code' in fields:
            data['JAMB Profile Code'] = student.jamb_profile_code or ''
        if 'jamb_reg_number' in fields:
            data['JAMB Reg Number'] = student.jamb_reg_number or ''
        if 'waec_reg_number' in fields:
            data['WAEC Reg Number'] = student.waec_reg_number or ''

        student_data.append(data)

    # Get ordered field names for export
    field_order = ['Student ID', 'Surname', 'First Name', 'Middle Name', 'Gender',
                   'Class', 'Date of Birth', 'Age', 'Religion', 'Home Address',
                   'Hobbies', 'Parent Phone',
                   'NIN', 'JAMB Profile Code', 'JAMB Reg Number', 'WAEC Reg Number']
    export_fields = [f for f in field_order if f in student_data[0]] if student_data else []
    
    if format_type == 'csv':
        import csv as _csv
        from io import StringIO
        from flask import Response
        buf = StringIO()
        writer = _csv.writer(buf)
        writer.writerow(export_fields)
        for row in student_data:
            writer.writerow([row.get(f, '') for f in export_fields])
        resp = Response(buf.getvalue(), mimetype='text/csv')
        resp.headers['Content-Disposition'] = 'attachment; filename=students.csv'
        return resp
    elif format_type == 'excel':
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
