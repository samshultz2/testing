// Shared contact-field validation, used by both the student and admissions
// applicant forms so their phone/email rules (and "Mr./Mrs." relationship
// inference) can never drift apart.

// Nigerian phone: 11 digits starting with 0, or +234/234 followed by 10
// digits (mirrors utils/security.py's validate_phone_number).
const PHONE_RE = /^(0[789][01]\d{8}|(\+?234)[789][01]\d{8})$/;
export const isValidPhone = (v) => PHONE_RE.test((v || '').replace(/[\s\-()]+/g, ''));

const EMAIL_RE = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
export const isValidEmail = (v) => EMAIL_RE.test((v || '').trim());

// "Mr. …" / "Mrs. …" name prefixes are a strong enough signal to pre-fill a
// relationship field. Callers treat the result as a default, freely
// overridable by the admin — never call this to force a value.
export function relationshipFromName(name) {
  const t = (name || '').trim();
  if (/^mrs\.?\s/i.test(t)) return 'Mother';
  if (/^mr\.?\s/i.test(t)) return 'Father';
  return null;
}
