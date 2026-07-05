"""subjects blueprint — crud routes (split from the former routes/subjects.py)."""
from routes.subjects import *  # noqa: F401,F403


@subjects_bp.route('/')
@login_required
def subjects_list():
    """List all subjects"""
    from utils.org_scope import scope_subjects
    subjects = scope_subjects(
        Subject.query.filter_by(is_active=True), Subject
    ).order_by(Subject.category, Subject.name).all()
    
    # Group by category
    categories = {}
    for subject in subjects:
        cat = subject.category or 'General'
        categories.setdefault(cat, []).append({
            'id': subject.id, 'name': subject.name, 'short_name': subject.short_name or '',
            'edit_url': url_for('subjects.edit_subject', subject_id=subject.id),
            'delete_url': url_for('subjects.delete_subject', subject_id=subject.id),
        })

    return _render({
        'page': 'list', 'nav': _nav_urls(),
        'categories': [{'name': k, 'subjects': v} for k, v in categories.items()],
        'urls': {'add': url_for('subjects.add_subject'),
                 'bulk_add': url_for('subjects.bulk_add_subjects')},
    })


@subjects_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_subject():
    """Add a new subject"""
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            short_name = request.form.get('short_name', '').strip().upper()
            category = request.form.get('category', '').strip()

            if not name:
                return _err('Subject name is required.', url_for('subjects.add_subject'))
            if Subject.query.filter_by(name=name).first():
                return _err('Subject already exists.', url_for('subjects.add_subject'))

            subject = Subject(
                name=name,
                short_name=short_name or name[:3].upper(),
                category=category or 'General',
                has_practical=bool(request.form.get('has_practical'))
            )
            db.session.add(subject)
            db.session.flush()
            from utils.assessments import apply_practical
            apply_practical(db, subject)
            db.session.commit()
            return _ok(f'Subject "{name}" added!', url_for('subjects.subjects_list'))
        except Exception as e:
            db.session.rollback()
            return _err(f'Error: {str(e)}', url_for('subjects.add_subject'))

    return _render({
        'page': 'add', 'nav': _nav_urls(), 'categories': SUBJECT_CATEGORIES,
        'submit_url': url_for('subjects.add_subject'), 'cancel_url': url_for('subjects.subjects_list'),
    })


@subjects_bp.route('/<int:subject_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_subject(subject_id):
    """Edit a subject"""
    subject = db.get_or_404(Subject, subject_id)

    if request.method == 'POST':
        try:
            subject.name = request.form.get('name', '').strip()
            subject.short_name = request.form.get('short_name', '').strip().upper()
            subject.category = request.form.get('category', '').strip()
            subject.has_practical = bool(request.form.get('has_practical'))
            from utils.assessments import apply_practical
            apply_practical(db, subject)
            db.session.commit()
            return _ok('Subject updated!', url_for('subjects.subjects_list'))
        except Exception as e:
            db.session.rollback()
            return _err(f'Error: {str(e)}', url_for('subjects.edit_subject', subject_id=subject_id))

    return _render({
        'page': 'edit', 'nav': _nav_urls(), 'categories': SUBJECT_CATEGORIES,
        'subject': {'id': subject.id, 'name': subject.name, 'short_name': subject.short_name or '',
                    'category': subject.category or 'General', 'has_practical': bool(subject.has_practical)},
        'submit_url': url_for('subjects.edit_subject', subject_id=subject.id),
        'cancel_url': url_for('subjects.subjects_list'),
    })


@subjects_bp.route('/<int:subject_id>/delete', methods=['POST'])
@login_required
def delete_subject(subject_id):
    """Delete (deactivate) a subject"""
    subject = db.get_or_404(Subject, subject_id)
    try:
        subject.is_active = False
        db.session.commit()
        from utils.audit import log_action
        log_action('subject.delete', detail=getattr(subject, 'name', None), target=subject)
        return _ok('Subject deleted!', url_for('subjects.subjects_list'))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('subjects.subjects_list'))


@subjects_bp.route('/bulk-add', methods=['GET', 'POST'])
@login_required
def bulk_add_subjects():
    """Bulk add subjects"""
    if request.method == 'POST':
        try:
            subjects_text = request.form.get('subjects', '')
            category = request.form.get('category', 'General')

            lines = [line.strip() for line in subjects_text.split('\n') if line.strip()]
            added = 0
            for line in lines:
                if not Subject.query.filter_by(name=line).first():
                    db.session.add(Subject(name=line, short_name=line[:3].upper(), category=category))
                    added += 1

            db.session.commit()
            return _ok(f'{added} subjects added!', url_for('subjects.subjects_list'))
        except Exception as e:
            db.session.rollback()
            return _err(f'Error: {str(e)}', url_for('subjects.bulk_add_subjects'))

    default_subjects = '\n'.join([
        'Mathematics', 'English Language', 'Civic Education', 'Physics', 'Chemistry', 'Biology',
        'Further Mathematics', 'Agricultural Science', 'Economics', 'Geography', 'Government',
        'Literature in English', 'Commerce', 'Accounting', 'Computer Studies',
        'Christian Religious Studies', 'Islamic Religious Studies', 'French', 'Yoruba', 'Igbo',
        'Hausa', 'Technical Drawing', 'Food and Nutrition', 'Home Economics', 'Physical Education',
        'History', 'Music', 'Visual Arts'])
    return _render({
        'page': 'bulk_add', 'nav': _nav_urls(), 'categories': SUBJECT_CATEGORIES,
        'default_subjects': default_subjects,
        'submit_url': url_for('subjects.bulk_add_subjects'), 'cancel_url': url_for('subjects.subjects_list'),
    })


@subjects_bp.route('/class-subjects')
@login_required
def class_subjects_list():
    """List class-subject assignments for a term"""
    term_id = request.args.get('term_id', type=int)
    class_id = request.args.get('class_id', type=int)
    
    terms = Term.query.order_by(Term.id.desc()).all()
    classes = SchoolClass.query.order_by(SchoolClass.level).all()
    
    # Get active term if not specified
    if not term_id:
        active_term = get_active_term()
        if active_term:
            term_id = active_term.id
    
    class_subjects = []
    selected_term = None
    selected_class = None
    
    if term_id:
        selected_term = db.session.get(Term, term_id)
        query = ClassSubject.query.filter_by(term_id=term_id, is_active=True)
        
        if class_id:
            selected_class = db.session.get(SchoolClass, class_id)
            query = query.filter_by(class_id=class_id)
        
        class_subjects = query.join(Subject).order_by(Subject.name).all()

    return _render({
        'page': 'class_subjects', 'nav': _nav_urls(),
        'term_id': term_id or '', 'class_id': class_id or '',
        'selected_term': selected_term.full_name if selected_term else '',
        'terms': [{'id': t.id, 'full_name': t.full_name} for t in terms],
        'classes': [{'id': c.id, 'name': c.name} for c in classes],
        'class_subjects': [{'id': cs.id, 'subject': cs.subject.name,
                            'class_name': cs.school_class.name if cs.school_class else '',
                            'arm': cs.arm.name if cs.arm else '', 'teacher_name': cs.teacher_name or '',
                            'edit_url': url_for('subjects.edit_class_subject', cs_id=cs.id),
                            'delete_url': url_for('subjects.delete_class_subject', cs_id=cs.id)}
                           for cs in class_subjects],
        'self_url': url_for('subjects.class_subjects_list'),
        'urls': {'assign': url_for('subjects.assign_class_subjects'),
                 'copy': url_for('subjects.copy_class_subjects')},
    })


@subjects_bp.route('/class-subjects/copy', methods=['POST'])
@login_required
def copy_class_subjects():
    """Copy subject assignments from one term into another (modifiable later)."""
    from_term_id = request.form.get('from_term_id', type=int)
    to_term_id = request.form.get('to_term_id', type=int)
    class_id = request.form.get('class_id', type=int)

    if not from_term_id or not to_term_id or from_term_id == to_term_id:
        return _err('Choose two different terms to copy between.',
                    url_for('subjects.class_subjects_list', term_id=to_term_id or '', class_id=class_id or ''))

    source = ClassSubject.query.filter_by(term_id=from_term_id, is_active=True)
    if class_id:
        source = source.filter_by(class_id=class_id)
    source = source.all()

    copied, skipped = 0, 0
    for cs in source:
        exists = ClassSubject.query.filter_by(
            term_id=to_term_id, class_id=cs.class_id, arm_id=cs.arm_id,
            subject_id=cs.subject_id
        ).first()
        if exists:
            skipped += 1
            continue
        db.session.add(ClassSubject(
            subject_id=cs.subject_id, class_id=cs.class_id, arm_id=cs.arm_id,
            term_id=to_term_id, teacher_name=cs.teacher_name, is_active=True))
        copied += 1
    db.session.commit()
    return _ok(f'Copied {copied} subject assignment(s){" (" + str(skipped) + " already existed)" if skipped else ""}.',
               url_for('subjects.class_subjects_list', term_id=to_term_id, class_id=class_id or ''))


@subjects_bp.route('/class-subjects/assign', methods=['GET', 'POST'])
@login_required
def assign_class_subjects():
    """Assign subjects to a class for a term"""
    if request.method == 'POST':
        try:
            term_id = request.form.get('term_id', type=int)
            class_id = request.form.get('class_id', type=int)
            arm_id = request.form.get('arm_id', type=int) or None
            subject_ids = request.form.getlist('subject_ids[]')
            teacher_names = request.form.getlist('teacher_names[]')
            
            if not term_id or not class_id:
                return _err('Term and class are required.', url_for('subjects.assign_class_subjects'))

            added = 0
            for i, subject_id in enumerate(subject_ids):
                if subject_id:
                    # Check if already exists
                    existing = ClassSubject.query.filter_by(
                        subject_id=int(subject_id),
                        class_id=class_id,
                        arm_id=arm_id,
                        term_id=term_id
                    ).first()
                    
                    if existing:
                        # Update teacher name
                        existing.teacher_name = teacher_names[i] if i < len(teacher_names) else None
                        existing.is_active = True
                    else:
                        cs = ClassSubject(
                            subject_id=int(subject_id),
                            class_id=class_id,
                            arm_id=arm_id,
                            term_id=term_id,
                            teacher_name=teacher_names[i] if i < len(teacher_names) else None
                        )
                        db.session.add(cs)
                        added += 1
            
            db.session.commit()
            return _ok(f'{added} subjects assigned!',
                       url_for('subjects.class_subjects_list', term_id=term_id, class_id=class_id))
        except Exception as e:
            db.session.rollback()
            return _err(f'Error: {str(e)}', url_for('subjects.assign_class_subjects'))

    terms = Term.query.order_by(Term.id.desc()).all()
    classes = SchoolClass.query.order_by(SchoolClass.level).all()
    arms = ClassArm.query.filter_by(is_default=False).order_by(ClassArm.name).all()
    subjects = Subject.query.filter_by(is_active=True).order_by(Subject.name).all()

    return _render({
        'page': 'assign', 'nav': _nav_urls(),
        'terms': [{'id': t.id, 'full_name': t.full_name, 'is_active': bool(t.is_active)} for t in terms],
        'classes': [{'id': c.id, 'name': c.name} for c in classes],
        'arms': [{'id': a.id, 'name': a.name} for a in arms],
        'subjects': [{'id': s.id, 'name': s.name, 'category': s.category or ''} for s in subjects],
        'submit_url': url_for('subjects.assign_class_subjects'),
        'cancel_url': url_for('subjects.class_subjects_list'),
    })


@subjects_bp.route('/class-subjects/<int:cs_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_class_subject(cs_id):
    """Edit class-subject assignment (mainly teacher name)"""
    cs = db.get_or_404(ClassSubject, cs_id)
    
    if request.method == 'POST':
        try:
            cs.teacher_name = request.form.get('teacher_name', '').strip() or None
            db.session.commit()
            return _ok('Updated!', url_for('subjects.class_subjects_list', term_id=cs.term_id, class_id=cs.class_id))
        except Exception as e:
            db.session.rollback()
            return _err(f'Error: {str(e)}', url_for('subjects.edit_class_subject', cs_id=cs.id))

    return _render({
        'page': 'edit_class_subject', 'nav': _nav_urls(),
        'cs': {'id': cs.id, 'subject': cs.subject.name,
               'class_name': cs.school_class.name if cs.school_class else '',
               'arm': cs.arm.name if cs.arm else 'All Arms',
               'term': cs.term.full_name if cs.term else '', 'teacher_name': cs.teacher_name or ''},
        'submit_url': url_for('subjects.edit_class_subject', cs_id=cs.id),
        'cancel_url': url_for('subjects.class_subjects_list', term_id=cs.term_id, class_id=cs.class_id),
    })


@subjects_bp.route('/class-subjects/<int:cs_id>/delete', methods=['POST'])
@login_required
def delete_class_subject(cs_id):
    """Remove class-subject assignment"""
    cs = db.get_or_404(ClassSubject, cs_id)
    term_id = cs.term_id
    class_id = cs.class_id

    try:
        cs.is_active = False
        db.session.commit()
        from utils.audit import log_action
        log_action('subject.class_unassign',
                   detail=f'class_subject={cs_id} term={term_id} class={class_id}',
                   target_type='classsubject', target_id=cs_id)
        return _ok('Subject removed from class!',
                   url_for('subjects.class_subjects_list', term_id=term_id, class_id=class_id))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}',
                    url_for('subjects.class_subjects_list', term_id=term_id, class_id=class_id))


@subjects_bp.route('/api/class-subjects/<int:term_id>/<int:class_id>')
@login_required
def api_class_subjects(term_id, class_id):
    """Get subjects for a class in a term"""
    class_subjects = ClassSubject.query.filter_by(
        term_id=term_id,
        class_id=class_id,
        is_active=True
    ).join(Subject).order_by(Subject.name).all()
    
    return jsonify([{
        'id': cs.id,
        'subject_id': cs.subject_id,
        'subject_name': cs.subject.name,
        'teacher_name': cs.teacher_name
    } for cs in class_subjects])
