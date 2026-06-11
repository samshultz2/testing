"""
AES-256-GCM field encryption for sensitive columns at rest.

Active only when ``FIELD_ENCRYPTION_KEY`` is configured. When it is absent the
:class:`EncryptedString` type passes values through unchanged (plaintext), so
the application works out of the box and encryption is purely opt-in — set the
key and run ``scripts/encrypt_portal_passwords.py`` to turn it on.

Format of an encrypted value:  ``enc:gcm1:<base64(nonce(12) + ciphertext + tag)>``
Anything without that prefix is treated as legacy plaintext and returned as-is,
so mixed (partly-migrated) data reads correctly.
"""
import base64
import hashlib
import os

_PREFIX = 'enc:gcm1:'


def _key():
    """Return a 32-byte key, or None when encryption is disabled."""
    raw = ''
    try:
        from config import Config
        raw = getattr(Config, 'FIELD_ENCRYPTION_KEY', '') or ''
    except Exception:
        raw = ''
    raw = raw or os.environ.get('FIELD_ENCRYPTION_KEY', '')
    if not raw:
        return None
    # Prefer a base64-encoded 32-byte key; otherwise derive 32 bytes from the
    # provided secret so any sufficiently strong passphrase also works.
    try:
        decoded = base64.b64decode(raw, validate=True)
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass
    return hashlib.sha256(raw.encode('utf-8')).digest()


def is_enabled():
    return _key() is not None


def encrypt(plaintext):
    """Encrypt a string. Returns the token, or the input unchanged if disabled."""
    if plaintext is None:
        return None
    key = _key()
    if key is None:
        return plaintext
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, str(plaintext).encode('utf-8'), None)
    return _PREFIX + base64.b64encode(nonce + ct).decode('ascii')


def decrypt(token):
    """Decrypt a token. Plaintext (non-prefixed) input is returned unchanged."""
    if token is None:
        return None
    if not isinstance(token, str) or not token.startswith(_PREFIX):
        return token
    key = _key()
    if key is None:
        return None   # encrypted data but no key — unrecoverable
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        blob = base64.b64decode(token[len(_PREFIX):])
        nonce, ct = blob[:12], blob[12:]
        return AESGCM(key).decrypt(nonce, ct, None).decode('utf-8')
    except Exception:
        return None


def looks_encrypted(value):
    return isinstance(value, str) and value.startswith(_PREFIX)
