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


def test_pii_columns_are_encrypted_text_type():
    """The sensitive PII columns are EncryptedString stored as TEXT (so the
    longer ciphertext fits and Postgres accepts it)."""
    from sqlalchemy import Text
    from models import StaffMember, Student
    from models.models import EncryptedString
    cols = [StaffMember.__table__.c.account_number, StaffMember.__table__.c.address,
            StaffMember.__table__.c.nok_phone, StaffMember.__table__.c.bank_name,
            StaffMember.__table__.c.notes, Student.__table__.c.home_address]
    for c in cols:
        assert isinstance(c.type, EncryptedString)
        assert isinstance(c.type.impl, Text)          # stored as TEXT (fits ciphertext)


def test_pii_columns_ciphertext_at_rest_and_roundtrip(with_key):
    """With the key set, the newly-encrypted PII columns are ciphertext at rest
    across student / staff / welfare, yet the ORM reads them back as plaintext.

    Uses a throwaway app/DB so the encrypted rows can't leak into other tests
    (once the key is restored they'd decrypt to None)."""
    import os as _os, tempfile as _tf
    from app import create_app
    from config import Config
    from models import StaffMember, DisciplineRecord
    from utils import crypto

    class _C(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + _os.path.join(_tf.mkdtemp(), 't.db')
    scratch = create_app(_C)
    with scratch.app_context():
        assert crypto.is_enabled()
        bid = Branch.get_default().id
        s = StaffMember(first_name='Ada', surname='Bello', is_active=True, branch_id=bid,
                        account_number='0123456789', bank_name='GTBank',
                        nok_phone='08012345678', address='12 Secret Road', notes='sensitive-note')
        stu = Student(student_id='ENC_PII_1', first_name='Kid', surname='One', gender='Male',
                      is_active=True, branch_id=bid, home_address='9 Private Lane')
        db.session.add_all([s, stu]); db.session.flush()
        dr = DisciplineRecord(student_id=stu.id, branch_id=bid,
                              description='sensitive incident', action_taken='counselled')
        db.session.add(dr); db.session.commit()
        sid, stid, drid = s.id, stu.id, dr.id

        raw = db.session.execute(db.text(
            'SELECT account_number, bank_name, nok_phone, address, notes '
            'FROM staff_members WHERE id=:i'), {'i': sid}).first()
        assert all(str(cell).startswith('enc:gcm1:') for cell in raw), raw
        assert db.session.execute(db.text('SELECT home_address FROM students WHERE id=:i'),
                                  {'i': stid}).first()[0].startswith('enc:gcm1:')
        assert db.session.execute(db.text('SELECT description FROM discipline_records WHERE id=:i'),
                                  {'i': drid}).first()[0].startswith('enc:gcm1:')

        db.session.expire_all()
        got = db.session.get(StaffMember, sid)
        assert got.account_number == '0123456789' and got.notes == 'sensitive-note'
        assert db.session.get(Student, stid).home_address == '9 Private Lane'
        assert db.session.get(DisciplineRecord, drid).description == 'sensitive incident'


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
