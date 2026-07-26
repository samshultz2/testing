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
    from models import TermResult, ClassSubject, Subject, Term, AcademicSession
    results = TermResult.query.filter_by(student_id=sid).all()
    cs = {c.id: c for c in ClassSubject.query.filter(
        ClassSubject.id.in_({r.class_subject_id for r in results if r.class_subject_id})).all()} if results else {}
    subjects = {s.id: s.name for s in Subject.query.filter(
        Subject.id.in_({c.subject_id for c in cs.values()})).all()} if cs else {}
    terms = {t.id: t for t in Term.query.filter(
        Term.id.in_({r.term_id for r in results if r.term_id})).all()} if results else {}
    sessions = {s.id: s.name for s in AcademicSession.query.filter(
        AcademicSession.id.in_({t.session_id for t in terms.values()})).all()} if terms else {}
    by_term, all_scores = {}, []
    for r in results:
        c = cs.get(r.class_subject_id)
        subj = subjects.get(c.subject_id, 'Subject') if c else 'Subject'
        t = terms.get(r.term_id)
        g = by_term.setdefault(r.term_id, {
            'term': t.name if t else '', 'term_number': t.term_number if t else 0,
            'session': (sessions.get(t.session_id) if t else '') or '', 'subjects': [], 'scores': []})
        g['subjects'].append({'subject': subj, 'score': r.total_score, 'grade': r.grade,
                              'position': r.position_in_subject, 'remark': r.remark,
                              'comment': r.teacher_comment})
        if r.total_score is not None:
            g['scores'].append(r.total_score); all_scores.append(r.total_score)
    out = []
    for g in by_term.values():
        g['subjects'].sort(key=lambda s: s['subject'])
        out.append({'term': g['term'], 'session': g['session'], 'term_number': g['term_number'],
                    'average': round(sum(g['scores']) / len(g['scores']), 1) if g['scores'] else None,
                    'subjects': g['subjects']})
    out.sort(key=lambda x: (x['session'], x['term_number']))
    cumulative = round(sum(all_scores) / len(all_scores), 1) if all_scores else None
    return {'cumulative': cumulative, 'terms_count': len(out), 'terms': out}


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
    sid = student.id
    bio = {
        'photo_url': student.photo_url or '',
        'date_of_birth': student.date_of_birth.strftime('%d %b %Y') if student.date_of_birth else '',
        'religion': student.religion or '', 'home_address': student.home_address or '',
        'house': student.house or '', 'boarding_status': student.boarding_status or '',
        'blood_group': student.blood_group or '', 'genotype': student.genotype or '',
        'allergies': student.allergies or '', 'nin': student.nin or '',
        'stream': student.stream or '', 'hobbies': student.hobbies or '',
        'waec_subjects': student.waec_subjects or '', 'jamb_subjects': student.jamb_subjects or '',
        'jamb_reg_number': student.jamb_reg_number or '',
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
        t['klass'] = klass_by.get((t['session'], t['term_number'])) or klass_by_session.get(t['session']) or ''
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
