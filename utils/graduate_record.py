"""Assemble a graduate's permanent, read-only record from the data already held
across the app: biodata, class/arm history, full academic history (per-term
subjects, positions, teacher comments, cumulative average), attendance, finance,
and discipline. Each section is defensive — one failing section never breaks the
whole record. Queries are batched (no N+1) so it stays fast for long histories.
"""
from __future__ import annotations


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def _class_history(sid):
    from models import (StudentEnrollment, ClassArmAssignment, SchoolClass,
                        ClassArm, Term, AcademicSession)
    enr = StudentEnrollment.query.filter_by(student_id=sid).all()
    caa_ids = [e.class_arm_assignment_id for e in enr if e.class_arm_assignment_id]
    caas = ({c.id: c for c in ClassArmAssignment.query.filter(ClassArmAssignment.id.in_(caa_ids)).all()}
            if caa_ids else {})
    classes = {c.id: c.name for c in SchoolClass.query.filter(
        SchoolClass.id.in_({c.class_id for c in caas.values()})).all()} if caas else {}
    arms = {a.id: a.name for a in ClassArm.query.filter(
        ClassArm.id.in_({c.arm_id for c in caas.values()})).all()} if caas else {}
    terms = {t.id: t for t in Term.query.filter(
        Term.id.in_({c.term_id for c in caas.values()})).all()} if caas else {}
    sessions = {s.id: s.name for s in AcademicSession.query.filter(
        AcademicSession.id.in_({t.session_id for t in terms.values()})).all()} if terms else {}
    rows = []
    for e in enr:
        c = caas.get(e.class_arm_assignment_id)
        if not c:
            continue
        t = terms.get(c.term_id)
        rows.append({'klass': classes.get(c.class_id, '—'), 'arm': arms.get(c.arm_id, ''),
                     'term': t.name if t else '', 'term_number': t.term_number if t else 0,
                     'session': (sessions.get(t.session_id) if t else '') or ''})
    rows.sort(key=lambda h: (h['session'], h['term_number']))
    return rows


def _academic(sid):
    """Per-term subject results, computed from the raw ``StudentScore`` rows the
    same way the broadsheet / report cards do: the subject total for a term is the
    sum of that subject's assessment scores. (The aggregated ``TermResult`` table
    is not populated in normal use, which is why the transcript used to be blank.)
    Each term is tagged with the class the subject belonged to (SSS1/SSS2/SSS3)."""
    from models import (StudentScore, ClassSubject, Subject, Term, AcademicSession,
                        SchoolClass, GradeScale)
    scores = StudentScore.query.filter_by(student_id=sid).all()
    if not scores:
        return {'cumulative': None, 'terms_count': 0, 'terms': []}
    cs_ids = {s.class_subject_id for s in scores if s.class_subject_id}
    cs = {c.id: c for c in ClassSubject.query.filter(ClassSubject.id.in_(cs_ids)).all()} if cs_ids else {}
    subjects = {s.id: s.name for s in Subject.query.filter(
        Subject.id.in_({c.subject_id for c in cs.values()})).all()} if cs else {}
    terms = {t.id: t for t in Term.query.filter(
        Term.id.in_({c.term_id for c in cs.values() if c.term_id})).all()} if cs else {}
    sessions = {s.id: s.name for s in AcademicSession.query.filter(
        AcademicSession.id.in_({t.session_id for t in terms.values()})).all()} if terms else {}
    classes = {c.id: c.name for c in SchoolClass.query.filter(
        SchoolClass.id.in_({c.class_id for c in cs.values() if c.class_id})).all()} if cs else {}
    # subject total for a (student, class_subject) = sum of its assessment scores
    totals = {}
    for s in scores:
        if s.class_subject_id:
            totals[s.class_subject_id] = totals.get(s.class_subject_id, 0) + (s.score or 0)
    # grade cache (one query per distinct rounded score)
    grade_cache = {}

    def grade_of(v):
        key = round(v)
        if key not in grade_cache:
            try:
                grade_cache[key] = GradeScale.get_grade(v)
            except Exception:
                grade_cache[key] = ''
        return grade_cache[key]

    by_term, all_scores = {}, []
    for cs_id, total in totals.items():
        c = cs.get(cs_id)
        if not c:
            continue
        t = terms.get(c.term_id)
        g = by_term.setdefault(c.term_id, {
            'term': t.name if t else '', 'term_number': t.term_number if t else 0,
            'session': (sessions.get(t.session_id) if t else '') or '',
            'klass': classes.get(c.class_id, ''), 'subjects': [], 'scores': []})
        total = round(total, 1)
        g['subjects'].append({'subject': subjects.get(c.subject_id, 'Subject'), 'score': total,
                              'grade': grade_of(total), 'position': None, 'remark': None, 'comment': None})
        g['scores'].append(total)
        all_scores.append(total)
    out = []
    for g in by_term.values():
        g['subjects'].sort(key=lambda s: s['subject'])
        out.append({'term': g['term'], 'session': g['session'], 'term_number': g['term_number'],
                    'klass': g['klass'],
                    'average': round(sum(g['scores']) / len(g['scores']), 1) if g['scores'] else None,
                    'subjects': g['subjects']})
    out.sort(key=lambda x: (x['session'], x['term_number']))
    cumulative = round(sum(all_scores) / len(all_scores), 1) if all_scores else None
    return {'cumulative': cumulative, 'terms_count': len(out), 'terms': out}


def _competence(sid):
    """The student's Mock WAEC (a.k.a. competence exam) results — per subject
    score + WAEC grade — taken from their latest/most-advanced mock exam. This is
    the SS3 'competence' column shown on transcripts."""
    from models import MockWAECResult, MockWAECExam
    rows = MockWAECResult.query.filter_by(student_id=sid).all()
    if not rows:
        return None
    exam_ids = {r.mock_exam_id for r in rows}
    exams = {e.id: e for e in MockWAECExam.query.filter(MockWAECExam.id.in_(exam_ids)).all()}
    if not exams:
        return None
    best = max(exams.values(), key=lambda e: (e.exam_number or 0, e.id))
    subjects = {r.subject: {'score': r.score, 'grade': r.grade}
                for r in rows if r.mock_exam_id == best.id}
    return {'label': getattr(best, 'display_name', 'Competence'), 'subjects': subjects}


def _attendance(sid):
    from models import db, StudentEnrollment, Attendance
    enr_ids = [e.id for e in StudentEnrollment.query.filter_by(student_id=sid).all()]
    if not enr_ids:
        return {'present': 0, 'total': 0, 'percent': None}
    rows = db.session.query(Attendance.morning_present, Attendance.afternoon_present) \
        .filter(Attendance.enrollment_id.in_(enr_ids)).all()
    present = total = 0
    for am, pm in rows:
        for v in (am, pm):
            if v is not None:
                total += 1
                if v:
                    present += 1
    return {'present': present, 'total': total,
            'percent': round(present / total * 100, 1) if total else None}


def _finance(sid):
    from models import FeePayment
    pays = FeePayment.query.filter_by(student_id=sid).order_by(FeePayment.payment_date.desc()).all()
    return {'total_paid': float(sum((p.amount or 0) for p in pays)), 'count': len(pays),
            'recent': [{'amount': float(p.amount or 0),
                        'date': p.payment_date.strftime('%d %b %Y') if p.payment_date else '',
                        'method': p.method or '', 'receipt': p.receipt_no or ''} for p in pays[:10]]}


def _discipline(sid):
    from models import DisciplineRecord
    rows = DisciplineRecord.query.filter_by(student_id=sid).order_by(DisciplineRecord.date.desc()).all()
    return [{'date': d.date.strftime('%d %b %Y') if d.date else '', 'category': d.category or '',
             'severity': d.severity or '', 'description': d.description or '',
             'action': d.action_taken or ''} for d in rows]


def build_record(student):
    """The full read-only permanent record for a graduate. Every section is
    best-effort; a section that errors comes back empty rather than 500-ing."""
    from models import ClinicVisit
    from utils import student_photo as _sp
    sid = student.id
    # Photos live in the StudentPhoto blob table and are served via the
    # /students/<id>/photo route; the student.photo_url column is unreliable
    # (often empty even when a photo exists), so build the served URL from a
    # real has_photo() check — matching how the students serializer does it.
    _photo = _sp.served_url(student) if _sp.has_photo(student) else (student.photo_url or '')
    bio = {
        'photo_url': _photo,
        'date_of_birth': student.date_of_birth.strftime('%d %b %Y') if student.date_of_birth else '',
        'religion': student.religion or '', 'home_address': student.home_address or '',
        'house': student.house or '', 'boarding_status': student.boarding_status or '',
        'blood_group': student.blood_group or '', 'genotype': student.genotype or '',
        'allergies': student.allergies or '', 'nin': student.nin or '',
        'stream': student.stream or '', 'hobbies': student.hobbies or '',
        'waec_subjects': student.waec_subjects or '', 'jamb_subjects': student.jamb_subjects or '',
        'jamb_reg_number': student.jamb_reg_number or '',
        'waec_reg_number': getattr(student, 'waec_reg_number', '') or '',
        'serial_number': getattr(student, 'serial_number', '') or '',
    }
    history = _safe(lambda: _class_history(sid), [])
    academic = _safe(lambda: _academic(sid), {'cumulative': None, 'terms_count': 0, 'terms': []})
    # Tag each academic term with the class the student was in that
    # session+term (from the class history), so a transcript can show the class
    # (SSS1/SSS2/SSS3) and scope itself to the senior-secondary years.
    klass_by = {(h['session'], h['term_number']): h['klass'] for h in history}
    klass_by_session = {}
    for h in history:
        klass_by_session.setdefault(h['session'], h['klass'])
    for t in academic.get('terms', []):
        if not t.get('klass'):
            t['klass'] = klass_by.get((t['session'], t['term_number'])) or klass_by_session.get(t['session']) or ''
    # SS3 competence (Mock WAEC) results, surfaced on the transcript alongside terms
    academic['competence'] = _safe(lambda: _competence(sid), None)
    return {
        'bio': bio,
        # admission (earliest) + graduation sessions bracket the school career
        'admission_session': (history[0]['session'] if history else ''),
        'class_history': history,
        'academic': academic,
        'attendance': _safe(lambda: _attendance(sid), {'present': 0, 'total': 0, 'percent': None}),
        'finance': _safe(lambda: _finance(sid), {'total_paid': 0, 'count': 0, 'recent': []}),
        'discipline': _safe(lambda: _discipline(sid), []),
        'clinic_visits': _safe(lambda: ClinicVisit.query.filter_by(student_id=sid).count(), 0),
    }
