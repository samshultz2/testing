"""School onboarding pipeline (Stages 1+3 glue).

Ties the registry (`utils.tenancy`) to provisioning (`utils.provisioning`) so a
school signup becomes fully automatic once its email is verified:

    request_school()  ->  pending + emailed verification link
    verify_and_provision(token)  ->  creates the database, subdomain becomes
                                     live, first admin created, credentials
                                     emailed — all in one call.

Nothing here runs during a normal request; it is invoked by the (future) public
registration route or the CLI. Kept separate from `tenancy` (pure registry) and
`provisioning` (pure database work).
"""
from __future__ import annotations

import secrets

from utils import tenancy, provisioning


def request_school(name, subdomain, admin_email):
    """A school signs up. Records it as pending and returns a verification token
    (which the caller emails). No database is created yet."""
    if not admin_email:
        raise ValueError('An admin email is required to register a school.')
    tenancy.register_tenant(name, subdomain, admin_email)
    token = secrets.token_urlsafe(32)
    tenancy.set_verification(subdomain, token)
    return tenancy.get_tenant(subdomain), token


def send_verification_email(tenant, token, verify_url):
    """Email the verification link (best-effort; no-op if mail isn't set up)."""
    try:
        from utils import mailer
        if not (mailer.is_configured() and tenant.admin_email):
            return False
        mailer.send_email(
            tenant.admin_email, 'Confirm your school registration',
            f'Hello,\n\nConfirm your registration for "{tenant.name}" by opening '
            f'this link:\n\n{verify_url}\n\nOnce confirmed, your school portal '
            f'and login will be set up automatically.\n')
        return True
    except Exception:
        return False


def verify_and_provision(subdomain, token, base_domain=None):
    """Email verified -> everything automatic: database created, subdomain live,
    first admin created. Returns (tenant, admin_username, temp_password).

    Raises ValueError on a bad/stale token or an already-active school.
    """
    t = tenancy.get_tenant(subdomain)
    if t is None:
        raise ValueError(f'No such school: {subdomain!r}')
    if t.status == 'active':
        raise ValueError(f'{subdomain!r} is already set up.')
    if not t.verification_token or not token or \
            not secrets.compare_digest(str(t.verification_token), str(token)):
        raise ValueError('This confirmation link is invalid or has already been used.')

    tenancy.mark_verified(subdomain)
    tenant, username, password = provisioning.provision(subdomain)   # DB + schema + admin
    _send_welcome_email(tenant, username, password, base_domain)
    return tenant, username, password


def _send_welcome_email(tenant, username, password, base_domain):
    try:
        from utils import mailer
        if not (mailer.is_configured() and tenant.admin_email):
            return
        url = f'https://{tenant.subdomain}.{base_domain}/' if base_domain else \
            f'(your school subdomain: {tenant.subdomain})'
        mailer.send_email(
            tenant.admin_email, f'{tenant.name} is ready',
            f'Your school portal is live at:\n\n  {url}\n\n'
            f'Sign in with:\n  username: {username}\n  temporary password: {password}\n\n'
            f'You will be asked to set a new password on first login.\n')
    except Exception:
        pass


def adopt_current_school(subdomain, name, database_url, admin_email=None):
    """Bring the EXISTING single school in as tenant #1 without touching its
    database — it is registered as active, pointing at its current database_url."""
    return tenancy.adopt_existing(subdomain, name, database_url, admin_email)
