"""Public certificate/transcript verification portal (Phase 2).

Anyone (an employer, a university) can confirm a graduate document is genuine by
scanning its QR code or entering its verification code — no login. Shows only the
minimum needed to confirm authenticity: the school, the graduate's name, the
document type, its number, and the issue date. A revoked or unknown code reports
'could not verify'. Tenant-aware: the code is looked up in the school DB that the
request's subdomain resolves to.
"""
from flask import Blueprint, render_template, request

from utils.security import rate_limited

graduate_verify_bp = Blueprint('graduate_verify', __name__)


@graduate_verify_bp.route('/verify')
@graduate_verify_bp.route('/verify/<code>')
@rate_limited('doc_verify', max_requests=30, window_minutes=15,
              global_max=600, global_window_minutes=15)
def verify(code=None):
    from models import db, GraduateDocument, AcademicSession
    from utils.school import school_profile
    code = (code or request.args.get('code') or '').strip().upper()
    doc = GraduateDocument.query.filter_by(verification_code=code).first() if code else None
    result = None
    if doc and not doc.revoked:
        s = doc.student
        grad_session = ''
        if s and s.graduation_session_id:
            gs = db.session.get(AcademicSession, s.graduation_session_id)
            grad_session = gs.name if gs else ''
        result = {
            'ok': True,
            'name': s.full_name if s else '',
            'doc_label': doc.label,
            'number': doc.document_number,
            'issued': doc.created_at.strftime('%d %B %Y') if doc.created_at else '',
            'graduation': grad_session or (s.graduation_date.strftime('%B %Y')
                                           if (s and s.graduation_date) else ''),
            'reprint': doc.reprint_count or 0,
        }
    elif doc and doc.revoked:
        result = {'ok': False, 'revoked': True}
    elif code:
        result = {'ok': False, 'revoked': False}
    return render_template('graduate_verify.html', result=result, code=code,
                           school=school_profile())
