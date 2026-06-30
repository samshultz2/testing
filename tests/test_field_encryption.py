"""AES-256-GCM field encryption: round-trip + plaintext pass-through. Portal
passwords are now HASH-ONLY (no recoverable copy at rest) — see the final test."""
import base64
import os

import pytest

from models import db, Branch, Student

KEY = base64.b64encode(b'0123456789abcdef0123456789abcdef').decode()  # 32 bytes


@pytest.fixture()
def with_key():
    old = os.environ.get('FIELD_ENCRYPTION_KEY')
    os.environ['FIELD_ENCRYPTION_KEY'] = KEY
    try:
        yield
    finally:
        if old is None:
            os.environ.pop('FIELD_ENCRYPTION_KEY', None)
        else:
            os.environ['FIELD_ENCRYPTION_KEY'] = old


def test_roundtrip_and_passthrough(with_key):
    from utils import crypto
    assert crypto.is_enabled()
    token = crypto.encrypt('Secret123')
    assert token != 'Secret123'
    assert crypto.looks_encrypted(token)
    assert crypto.decrypt(token) == 'Secret123'
    # legacy plaintext (no prefix) is returned unchanged
    assert crypto.decrypt('plain-value') == 'plain-value'
    assert crypto.encrypt(None) is None and crypto.decrypt(None) is None


def test_disabled_passthrough():
    from utils import crypto
    os.environ.pop('FIELD_ENCRYPTION_KEY', None)
    assert not crypto.is_enabled()
    assert crypto.encrypt('abc') == 'abc'   # stored as-is when disabled


def test_portal_password_is_hash_only(app):
    """Setting a portal password stores ONLY the one-way hash — there is no
    recoverable plaintext copy anywhere (the old portal_password_plain column is
    gone from the model), yet login verification still works."""
    with app.app_context():
        bid = Branch.get_default().id
        s = Student(student_id='HASH_PW', first_name='Hash', surname='Only',
                    gender='Male', is_active=True, branch_id=bid)
        s.set_portal_password('Hunter2!')
        db.session.add(s); db.session.commit()

        # No recoverable copy is mapped on the model at all.
        assert not hasattr(s, 'portal_password_plain')
        # The stored hash is one-way (does not contain the raw PIN) and verifies.
        assert s.portal_password_hash and 'Hunter2!' not in s.portal_password_hash
        assert s.check_portal_password('Hunter2!')
        assert not s.check_portal_password('wrong')
