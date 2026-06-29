"""results blueprint — cutoffs routes (split from the former routes/results.py)."""
from routes.results import *  # noqa: F401,F403


@results_bp.route('/cutoffs')
@login_required
def cutoffs_list():
    """Manage university/course admission cut-offs used by the advisor."""
    universities = [u[0] for u in db.session.query(UniversityCutoff.university_name)
                    .distinct().order_by(UniversityCutoff.university_name).all()]
    if 'General Requirements' not in universities:
        universities.insert(0, 'General Requirements')
    selected = request.args.get('university') or universities[0]
    rows = UniversityCutoff.query.filter_by(university_name=selected).order_by(
        UniversityCutoff.faculty, UniversityCutoff.course_name).all()

    edit_id = request.args.get('edit', type=int)
    editing = db.session.get(UniversityCutoff, edit_id) if edit_id else None
    editing_subjects = _json.loads(editing.required_subjects or '[]') if editing else []
    reference = SchoolSettings.get('admission_reference', 'General Requirements')

    return _render({
        'page': 'cutoffs', 'is_admin': _is_admin_results(),
        'universities': universities, 'selected': selected, 'reference': reference,
        'subjects': list(WAEC_SUBJECTS),
        'rows': [{'id': r.id, 'course_name': r.course_name, 'faculty': r.faculty or '',
                  'jamb_cutoff': r.jamb_cutoff, 'min_credits': r.min_credits,
                  'required_subjects': _json.loads(r.required_subjects or '[]'),
                  'edit_url': url_for('results.cutoffs_list', university=selected, edit=r.id),
                  'delete_url': url_for('results.cutoffs_delete', cid=r.id)} for r in rows],
        'editing': ({'id': editing.id, 'university_name': editing.university_name,
                     'course_name': editing.course_name, 'faculty': editing.faculty or '',
                     'jamb_cutoff': editing.jamb_cutoff, 'min_credits': editing.min_credits,
                     'exam_year': editing.exam_year, 'required_subjects': editing_subjects}
                    if editing else None),
        'self_url': url_for('results.cutoffs_list'),
        'urls': {'save': url_for('results.cutoffs_save'),
                 'reference': url_for('results.cutoffs_reference'),
                 'analytics': url_for('results.analytics_hub')},
    })


@results_bp.route('/cutoffs/save', methods=['POST'])
@admin_required
def cutoffs_save():
    cid = request.form.get('id', type=int)
    uni = (request.form.get('university_name') or '').strip() or 'General Requirements'
    course = (request.form.get('course_name') or '').strip()
    if not course:
        return _err('Course name is required.', url_for('results.cutoffs_list', university=uni))

    year = request.form.get('exam_year', type=int) or 0
    obj = db.session.get(UniversityCutoff, cid) if cid else None
    if not obj:
        obj = UniversityCutoff.query.filter_by(university_name=uni, course_name=course, exam_year=year).first()
    if not obj:
        obj = UniversityCutoff(university_name=uni, course_name=course, exam_year=year)
        db.session.add(obj)

    obj.university_name = uni
    obj.course_name = course
    obj.exam_year = year
    obj.faculty = (request.form.get('faculty') or '').strip() or None
    obj.jamb_cutoff = request.form.get('jamb_cutoff', type=int)
    obj.min_credits = request.form.get('min_credits', type=int) or 5
    obj.required_subjects = _json.dumps(request.form.getlist('required_subjects[]'))
    try:
        db.session.commit()
        log_action('cutoff_save', f'{uni} / {course}')
        return _ok(f'Saved cut-off for {course}.', url_for('results.cutoffs_list', university=uni))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('results.cutoffs_list', university=uni))


@results_bp.route('/cutoffs/<int:cid>/delete', methods=['POST'])
@admin_required
def cutoffs_delete(cid):
    obj = db.session.get(UniversityCutoff, cid)
    if obj:
        uni = obj.university_name
        db.session.delete(obj)
        db.session.commit()
        return _ok('Cut-off deleted.', url_for('results.cutoffs_list', university=uni))
    return _ok('Cut-off deleted.', url_for('results.cutoffs_list'))


@results_bp.route('/cutoffs/reference', methods=['POST'])
@admin_required
def cutoffs_reference():
    ref = (request.form.get('reference') or 'General Requirements').strip()
    SchoolSettings.set('admission_reference', ref, 'string',
                       'University reference used by the admission advisor')
    return _ok(f'Admission advisor now uses "{ref}" cut-offs.',
               url_for('results.cutoffs_list', university=ref))
