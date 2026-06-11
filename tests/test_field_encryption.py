"""AES-256-GCM field encryption: round-trip, plaintext pass-through, and
transparent encryption of Student.portal_password_plain at rest."""
import base64
import os

import pytest

from models import db, Branch, Student
from sqlalchemy import text

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


def test_portal_password_encrypted_at_rest(app, with_key):
    with app.app_context():
        bid = Branch.get_default().id
        s = Student(student_id='ENC_PW', first_name='Enc', surname='Pw',
                    gender='Male', is_active=True, branch_id=bid)
        s.set_portal_password('Hunter2!')
        db.session.add(s); db.session.commit()
        sid = s.id

        # Raw column value is ciphertext...
        raw = db.session.execute(
            text('SELECT portal_password_plain FROM students WHERE id = :id'),
            {'id': sid}).scalar()
        assert raw is not None and raw.startswith('enc:gcm1:')
        assert 'Hunter2!' not in raw

        # ...but the ORM transparently decrypts it.
        db.session.expire_all()
        again = db.session.get(Student, sid)
        assert again.portal_password_plain == 'Hunter2!'
        assert again.check_portal_password('Hunter2!')
