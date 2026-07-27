"""Public certificate/transcript verification portal (Phase 2).

Anyone (an employer, a university) can confirm a graduate document is genuine by
scanning its QR code or entering its verification code — no login. Shows only the
minimum needed to confirm authenticity: the school, the graduate's name, the
document type, its number, and the issue date. A revoked or unknown code reports
'could not verify'. Tenant-aware: the code is looked up in the school DB that the
request's subdomain resolves to.

Every attempt is recorded to a privacy-friendly audit trail (see
:class:`models.DocumentVerification`) so the school can see genuine third-party
checks and spot suspicious activity — writes are best-effort and never break the
public page.
"""
import hashlib

from flask import Blueprint, current_app, render_template, request

from utils.security import rate_limited

graduate_verify_bp = Blueprint('graduate_verify', __name__)


def _visitor_hash(req):
    """A salted, daily-rotating digest of IP+UA. It rotates every day and cannot
    be reversed to identify anyone — it exists only to group repeat checks by the
    same viewer within a day."""
    from datetime import date
    secret = current_app.config.get('SECRET_KEY', '') or 'doc-verify'
    fwd = req.headers.get('X-Forwarded-For', '')
    ip = (fwd.split(',')[0].strip() if fwd else (req.remote_addr or '')).strip()
    raw = f'{date.today().isoformat()}|{secret}|{ip}|{req.headers.get("User-Agent", "")}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _record(code, doc, result, source):
    """Append one verification attempt. Best-effort: swallow every error so a
    logging failure can never break the public verification page."""
    try:
        from models import db, DocumentVerification
        ref = (request.headers.get('Referer') or request.headers.get('Referrer') or '')[:120]
        db.session.add(DocumentVerification(
            code=(code or '')[:24],
            document_id=(doc.id if doc else None),
            student_id=(doc.student_id if doc else None),
            doc_type=(doc.doc_type if doc else None),
            result=result, source=source,
            visitor_hash=_visitor_hash(request), referrer=ref or None))
        db.session.commit()
    except Exception:
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass


@graduate_verify_bp.route('/verify')
@graduate_verify_bp.route('/verify/<code>')
@rate_limited('doc_verify', max_requests=30, window_minutes=15,
              global_max=600, global_window_minutes=15)
def verify(code=None):
    from models import db, GraduateDocument, AcademicSession
    from utils.school import school_profile
    # A code in the path means the QR link was scanned; via the form it's manual.
    source = 'qr' if code else 'manual'
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
        _record(code, doc, 'valid', source)
    elif doc and doc.revoked:
        result = {'ok': False, 'revoked': True}
        _record(code, doc, 'revoked', source)
    elif code:
        result = {'ok': False, 'revoked': False}
        _record(code, None, 'not_found', source)
    return render_template('graduate_verify.html', result=result, code=code,
                           school=school_profile())
