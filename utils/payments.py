"""Online fee collection (parents → their school) — provider-agnostic facade.

Each school picks a payment provider (Paystack / Flutterwave / Monnify) and stores
that provider's own keys, per-school, in its database (SchoolSettings) with the
secret encrypted at rest. This module resolves the active provider + keys and
delegates the real work to utils.payment_gateways. The public API
(is_configured / public_key / initialize / verify / verify_webhook) is unchanged,
so the parent portal and finance routes don't care which gateway is in use.

Separate from the platform SUBSCRIPTION billing (utils/billing.py), which uses the
PLATFORM_PAYSTACK_* keys — schools paying the platform, not parents paying schools.

Backward compatible: schools already configured for Paystack keep working with no
change (their keys live under paystack_* and the default provider is paystack).
"""
import secrets

from config import Config
from utils import payment_gateways as gw

PROVIDER_SETTING = 'payment_provider'


def active_provider():
    try:
        from models import SchoolSettings
        p = (SchoolSettings.get(PROVIDER_SETTING, '') or '').strip().lower()
        if p in gw.PROVIDERS:
            return p
    except Exception:
        pass
    return 'paystack'


def _s(key, default=''):
    from models import SchoolSettings
    return SchoolSettings.get(key, default)


def provider_keys(provider=None):
    """{'public','secret','extra'} for a provider (secret + extra decrypted)."""
    provider = provider or active_provider()
    pub = sec = extra = ''
    try:
        from utils import crypto
        pub = (_s(f'{provider}_public_key', '') or '').strip()
        rawsec = _s(f'{provider}_secret_key', '') or ''
        sec = (crypto.decrypt(rawsec) or '').strip() if rawsec else ''
        rawx = _s(f'{provider}_extra', '') or ''
        extra = (crypto.decrypt(rawx) or '').strip() if rawx else ''
    except Exception:
        pub = sec = extra = ''
    # Single-school (non-multi-tenant) Paystack falls back to env keys.
    if provider == 'paystack' and not sec and not Config.MULTI_TENANT:
        pub = pub or (Config.PAYSTACK_PUBLIC_KEY or '')
        sec = Config.PAYSTACK_SECRET_KEY or ''
    return {'public': pub, 'secret': sec, 'extra': extra}


def is_configured():
    k = provider_keys()
    prov = active_provider()
    if prov == 'monnify':
        return bool(k['secret'] and k['public'] and k['extra'])   # apiKey+secret+contractCode
    return bool(k['secret'])


def public_key():
    return provider_keys()['public']


def secret_key():
    return provider_keys()['secret']


def save_keys(provider, public_key_value, secret_key_value, extra_value=None):
    """Persist this school's keys for a provider and make it the active provider.
    Blank secret/extra means 'leave the stored value unchanged'."""
    from models import SchoolSettings
    from utils import crypto
    provider = provider if provider in gw.PROVIDERS else 'paystack'
    SchoolSettings.set(PROVIDER_SETTING, provider, 'string', 'Active payment provider')
    SchoolSettings.set(f'{provider}_public_key', (public_key_value or '').strip(),
                       'string', f'{provider} public key')
    sec = (secret_key_value or '').strip()
    if sec:
        SchoolSettings.set(f'{provider}_secret_key', crypto.encrypt(sec), 'string',
                           f'{provider} secret key (encrypted)')
    if extra_value is not None and extra_value.strip():
        SchoolSettings.set(f'{provider}_extra', crypto.encrypt(extra_value.strip()), 'string',
                           f'{provider} extra credential (encrypted)')


def clear_keys(provider=None):
    from models import SchoolSettings
    provider = provider or active_provider()
    SchoolSettings.set(f'{provider}_public_key', '', 'string')
    SchoolSettings.set(f'{provider}_secret_key', '', 'string')
    SchoolSettings.set(f'{provider}_extra', '', 'string')


def new_reference(prefix='PSK'):
    return f'{prefix}-{secrets.token_hex(8)}'


def initialize(email, amount_naira, reference, callback_url, metadata=None):
    if not is_configured():
        return {'ok': False, 'error': 'Online payment is not configured.'}
    return gw.initialize(active_provider(), provider_keys(), email=email, amount_naira=amount_naira,
                         reference=reference, callback_url=callback_url, metadata=metadata or {})


def verify(reference):
    if not is_configured():
        return {'ok': False, 'error': 'Online payment is not configured.'}
    return gw.verify(active_provider(), provider_keys(), reference)


def verify_webhook(headers, body):
    """Validate + parse an incoming provider webhook for the active provider.
    Returns {'ok': signature_valid, 'event': {...}}."""
    return gw.verify_webhook(active_provider(), provider_keys(), headers, body)
