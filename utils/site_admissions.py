"""Public admissions intake for the Website Builder.

Turns a public application form into an ``Applicant`` in the school's existing
Admissions module — no parallel workflow, no duplicate data. Configuration
(open/closed, intro, intended session, application fee) lives in SchoolSettings
so it's edited once and reused. When a fee is set and online payments are
configured, the applicant is created only AFTER the school's Paystack rail
verifies the payment (pay-first), and the fee is booked to Finance idempotently.
"""
from datetime import datetime, date

from models import db, SchoolSettings, Applicant, Branch, SchoolClass, AcademicSession

_MAXLEN = {'first_name': 60, 'surname': 60, 'middle_name': 60, 'parent_name': 100,
           'parent_phone': 20, 'parent_email': 120, 'previous_school': 150, 'address': 255}


def settings():
    g = SchoolSettings.get
    try:
        fee = float(g('web_admissions_fee', '0') or 0)
    except (TypeError, ValueError):
        fee = 0.0
    sid = g('web_admissions_session_id', '') or ''
    return {
        'open': g('web_admissions_open', '0') in ('1', 'true', 'on', True),
        'intro': g('web_admissions_intro', '') or '',
        'fee': fee,
        'session_id': int(sid) if str(sid).isdigit() else None,
    }


def save_settings(*, is_open, intro, fee, session_id):
    SchoolSettings.set('web_admissions_open', '1' if is_open else '0', 'string')
    SchoolSettings.set('web_admissions_intro', (intro or '')[:600], 'string')
    try:
        fee = max(0.0, float(fee or 0))
    except (TypeError, ValueError):
        fee = 0.0
    SchoolSettings.set('web_admissions_fee', str(fee), 'string')
    SchoolSettings.set('web_admissions_session_id', str(session_id or ''), 'string')
    db.session.commit()


def class_choices():
    """Classes an applicant can choose (id, name)."""
    try:
        return [(c.id, c.name) for c in SchoolClass.query.order_by(SchoolClass.name).all()]
    except Exception:
        return []


def validate(form):
    """Return (clean, errors) for a submitted application form."""
    errors = {}
    clean = {}
    for key in ('first_name', 'surname', 'middle_name', 'parent_name', 'parent_phone',
                'parent_email', 'previous_school', 'address'):
        clean[key] = (form.get(key) or '').strip()[:_MAXLEN[key]]
    if not clean['first_name']:
        errors['first_name'] = 'Required'
    if not clean['surname']:
        errors['surname'] = 'Required'
    if not clean['parent_name']:
        errors['parent_name'] = 'Required'
    if not clean['parent_phone'] and not clean['parent_email']:
        errors['parent_phone'] = 'Give a phone number or email so the school can reach you'
    if clean['parent_email'] and '@' not in clean['parent_email']:
        errors['parent_email'] = 'Enter a valid email'
    clean['gender'] = (form.get('gender') or '').strip()[:10]
    dob = (form.get('date_of_birth') or '').strip()
    clean['date_of_birth'] = None
    if dob:
        try:
            clean['date_of_birth'] = datetime.strptime(dob, '%Y-%m-%d').date()
        except ValueError:
            errors['date_of_birth'] = 'Use the date picker'
    cid = form.get('intended_class_id')
    clean['intended_class_id'] = int(cid) if (cid and str(cid).isdigit()) else None
    return clean, errors


def create_applicant(clean, *, fee_paid=0.0, fee_reference=None):
    """Create the Applicant from validated data (source=Website). Books the
    application fee to Finance when one was paid."""
    cfg = settings()
    a = Applicant(
        application_no=Applicant.generate_application_no(),
        branch_id=(Branch.get_default().id if Branch.get_default() else None),
        first_name=clean['first_name'], surname=clean['surname'],
        middle_name=clean['middle_name'] or None, gender=clean['gender'] or None,
        date_of_birth=clean['date_of_birth'],
        session_id=cfg['session_id'], intended_class_id=clean['intended_class_id'],
        previous_school=clean['previous_school'] or None, source='Website',
        status='Applied', applied_date=date.today(),
        parent_name=clean['parent_name'] or None, parent_phone=clean['parent_phone'] or None,
        parent_email=clean['parent_email'] or None, address=clean['address'] or None,
    )
    db.session.add(a)
    db.session.commit()
    if fee_paid and fee_reference:
        try:
            from utils import finance_ledger
            finance_ledger.post(finance_ledger.REVENUE, fee_paid, source_module='admissions',
                                category='Application Fee', method='Online',
                                branch_id=a.branch_id, origin_type='admission_fee',
                                origin_id=a.id, reference=fee_reference,
                                description=f'Application fee — {a.full_name}')
            db.session.commit()
        except Exception:
            db.session.rollback()
    return a


def find_application(application_no, surname):
    """Public status lookup: match by application number AND surname (so one
    can't enumerate others' applications with just a guessed number)."""
    if not application_no or not surname:
        return None
    a = Applicant.query.filter_by(application_no=application_no.strip()).first()
    if a and (a.surname or '').strip().lower() == surname.strip().lower():
        return a
    return None
