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
import base64
import hashlib
import io

from flask import (Blueprint, current_app, render_template, request, url_for,
                   send_file, abort)

from utils.security import rate_limited

graduate_verify_bp = Blueprint('graduate_verify', __name__)


def _qr_data_url(value):
    """A small PNG QR of ``value`` as a data: URL for inline use on the public
    page (no external request, works offline). None if qrcode is unavailable."""
    try:
        import qrcode
        img = qrcode.make(str(value or ''))
        buf = io.BytesIO(); img.save(buf, 'PNG'); buf.seek(0)
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')
    except Exception:
        return None


def _verify_abs_url(code):
    """Absolute URL of the verification page for a code (for the QR + receipt)."""
    try:
        return url_for('graduate_verify.verify', code=code, _external=True)
    except Exception:
        return (request.url_root.rstrip('/') + '/verify/' + (code or ''))


def _lookup(code):
    """Resolve a code to (doc, result-dict). result is None for an empty code,
    else a dict with ok/revoked and — when valid — the public summary plus a
    privacy-safe verification-count trust signal. Does not record the attempt."""
    from models import db, GraduateDocument, AcademicSession, DocumentVerification
    doc = GraduateDocument.query.filter_by(verification_code=code).first() if code else None
    if doc and not doc.revoked:
        s = doc.student
        grad_session = ''
        if s and s.graduation_session_id:
            gs = db.session.get(AcademicSession, s.graduation_session_id)
            grad_session = gs.name if gs else ''
        # Privacy-safe trust signal: how many genuine checks this document has had
        # (aggregate only — never who). Excludes the current attempt (recorded after).
        vq = DocumentVerification.query.filter_by(document_id=doc.id, result='valid')
        prior = vq.count()
        first = vq.order_by(DocumentVerification.created_at.asc()).first()
        result = {
            'ok': True,
            'name': s.full_name if s else '',
            'doc_label': doc.label,
            'number': doc.document_number,
            'issued_by': doc.issued_by or '',
            'issued': doc.created_at.strftime('%d %B %Y') if doc.created_at else '',
            'graduation': grad_session or (s.graduation_date.strftime('%B %Y')
                                           if (s and s.graduation_date) else ''),
            'reprint': doc.reprint_count or 0,
            'verify_count': prior + 1,   # counting this confirmation
            'first_checked': (first.created_at.strftime('%d %b %Y')
                              if first and first.created_at else None),
        }
        return doc, result
    if doc and doc.revoked:
        return doc, {'ok': False, 'revoked': True}
    if code:
        return None, {'ok': False, 'revoked': False}
    return None, None


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
    from utils.school import school_profile
    # A code in the path means the QR link was scanned; via the form it's manual.
    source = 'qr' if code else 'manual'
    code = (code or request.args.get('code') or '').strip().upper()
    doc, result = _lookup(code)
    if result and result.get('ok'):
        _record(code, doc, 'valid', source)
    elif result and result.get('revoked'):
        _record(code, doc, 'revoked', source)
    elif code:
        _record(code, None, 'not_found', source)
    verify_url = _verify_abs_url(code) if (result and result.get('ok')) else None
    return render_template(
        'graduate_verify.html', result=result, code=code,
        school=school_profile(), verify_url=verify_url,
        qr_data_url=_qr_data_url(verify_url) if verify_url else None,
        receipt_url=(url_for('graduate_verify.verify_receipt', code=code)
                     if (result and result.get('ok')) else None))


@graduate_verify_bp.route('/verify/<code>/receipt')
@rate_limited('doc_verify_receipt', max_requests=20, window_minutes=15,
              global_max=400, global_window_minutes=15)
def verify_receipt(code):
    """Download a branded PDF receipt confirming this verification. Only genuine
    (non-revoked, known) documents can produce a receipt."""
    from datetime import datetime
    from utils.school import school_profile, document_branding
    from utils import verify_receipt as vr
    code = (code or '').strip().upper()
    doc, result = _lookup(code)
    if not (result and result.get('ok')):
        abort(404)
    _record(code, doc, 'valid', 'receipt')
    try:
        branding = document_branding()
    except Exception:
        branding = {}
    checked_at = datetime.now().strftime('%d %B %Y, %H:%M')
    buf = vr.render_receipt(
        school=school_profile(), branding=branding, result=result, code=code,
        verify_url=_verify_abs_url(code), checked_at=checked_at)
    return send_file(buf, mimetype='application/pdf', as_attachment=True,
                     download_name='verification_%s.pdf' % code)
