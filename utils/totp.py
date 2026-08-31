"""RFC-6238 TOTP (time-based one-time passwords), stdlib-only.

Implemented with hmac/hashlib so we don't add a `pyotp` dependency. Compatible
with Google Authenticator / Authy / 1Password etc. (SHA1, 30-second step,
6 digits — the universal defaults).
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time as _time

DIGITS = 6
PERIOD = 30          # seconds per step
_ALG = hashlib.sha1  # the otpauth default authenticators assume


def generate_secret(length=20):
    """A fresh base32 secret (no padding) — 20 random bytes = 160 bits."""
    return base64.b32encode(secrets.token_bytes(length)).decode('ascii').rstrip('=')


def _b32decode(secret):
    s = (secret or '').strip().replace(' ', '').upper()
    pad = '=' * (-len(s) % 8)
    return base64.b32decode(s + pad, casefold=True)


def totp_at(secret, for_time=None, counter_offset=0):
    """The 6-digit code for a given UNIX time (default: now)."""
    if for_time is None:
        for_time = _time.time()
    counter = int(for_time) // PERIOD + counter_offset
    key = _b32decode(secret)
    msg = struct.pack('>Q', counter)
    digest = hmac.new(key, msg, _ALG).digest()
    offset = digest[-1] & 0x0F
    code_int = (struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** DIGITS)
    return str(code_int).zfill(DIGITS)


def verify(secret, code, window=1, for_time=None):
    """True if `code` matches the current step (or ±`window` steps for clock
    skew). Constant-time compare per candidate; tolerant of spaces/dashes."""
    if not secret or not code:
        return False
    cleaned = ''.join(ch for ch in str(code) if ch.isdigit())
    if len(cleaned) != DIGITS:
        return False
    try:
        for off in range(-window, window + 1):
            if hmac.compare_digest(cleaned, totp_at(secret, for_time, off)):
                return True
    except Exception:
        return False
    return False


def provisioning_uri(secret, account_name, issuer='EduSyncra'):
    """`otpauth://` URI for the QR code an authenticator app scans."""
    from urllib.parse import quote
    label = quote(f'{issuer}:{account_name}')
    iss = quote(issuer)
    return (f'otpauth://totp/{label}?secret={secret}&issuer={iss}'
            f'&algorithm=SHA1&digits={DIGITS}&period={PERIOD}')
