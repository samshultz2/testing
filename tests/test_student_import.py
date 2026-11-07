"""Paste-to-import students: flexible headings, preview then commit.

The route reuses the shared row importer in utils.excel_utils (gender default,
phone leading-zero restore, name+DOB de-duplication), so these tests focus on
the paste/preview/commit wiring on top of it.
"""
import re

from config import Config
from models import db, Student
from tests.conftest import login_token


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def _ptoken(client):
    html = client.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def _post(client, **data):
    data.setdefault('_csrf_token', _ptoken(client))
    return client.post('/students/import', headers={'X-Requested-With': 'fetch'}, data=data)


def test_preview_then_commit_partial_headings(app):
    client = _admin(app)
    # Two name headings + an unknown column + a ragged/blank row.
    text = ('Surname, First Name, Gender, Nickname\n'
            'Okafor, Chidi, Male, Chy\n'
            'Bello, Aisha, female\n'
            ', ,')
    pre = _post(client, text=text).get_json()
    assert pre['ok'] and pre['preview'] is True
    assert pre['valid'] == 2 and pre['invalid'] == 0   # blank row dropped, not counted
    assert 'surname' in pre['recognised'] and pre['ignored'] == ['Nickname']

    with app.app_context():
        before = Student.query.count()
    res = _post(client, text=text, commit='1').get_json()
    assert res['ok'] and res['created'] == 2
    with app.app_context():
        assert Student.query.count() == before + 2
        s = Student.query.filter_by(surname='Okafor', first_name='Chidi').first()
        assert s.gender == 'Male' and s.student_id.startswith('STU')


def test_only_surname_and_first_name(app):
    client = _admin(app)
    text = 'surname,first name\nAdeyemi,Tunde'
    res = _post(client, text=text, commit='1').get_json()
    assert res['ok'] and res['created'] == 1
    with app.app_context():
        s = Student.query.filter_by(surname='Adeyemi', first_name='Tunde').first()
        assert s is not None and s.gender == 'Unknown'   # no gender column -> defaulted


def test_same_name_no_dob_different_address_both_import(app):
    """Two genuinely different students sharing a name but with no DOB must NOT
    be merged by the duplicate guard — the home address disambiguates them.
    A true re-import (same name + same address) is still skipped."""
    client = _admin(app)
    text = ('Surname, First Name, Address\n'
            'Bello, Musa, "12 Allen Avenue"\n'
            'Bello, Musa, "7 Lekki Phase 1"')
    res = _post(client, text=text, commit='1').get_json()
    assert res['ok'] and res['created'] == 2   # both kept, not collapsed
    with app.app_context():
        assert Student.query.filter_by(surname='Bello', first_name='Musa').count() == 2
    # Re-importing the exact same list creates nobody new.
    res2 = _post(client, text=text, commit='1').get_json()
    assert res2['ok'] and res2['created'] == 0


def test_reimport_after_soft_delete_recreates(app):
    """A soft-deleted (trashed) student must not block re-importing them —
    otherwise deleting a class to re-add it reports every row as a duplicate."""
    client = _admin(app)
    text = 'Surname, First Name\nDangote, Aliko'
    assert _post(client, text=text, commit='1').get_json()['created'] == 1
    with app.app_context():
        s = Student.query.filter_by(surname='Dangote', first_name='Aliko').first()
        s.is_active = False   # soft-delete (what delete / trash does)
        db.session.commit()
    # Re-import now recreates the student rather than skipping it as a duplicate.
    res = _post(client, text=text, commit='1').get_json()
    assert res['ok'] and res['created'] == 1
    with app.app_context():
        assert Student.query.filter_by(surname='Dangote', first_name='Aliko',
                                       is_active=True).count() == 1


def test_tab_separated_with_phone_creates_contact(app):
    client = _admin(app)
    text = 'Surname\tFirst Name\tParent Phone\nJohnson\tMary\t8099887766'
    res = _post(client, text=text, commit='1').get_json()
    assert res['ok'] and res['created'] == 1
    with app.app_context():
        s = Student.query.filter_by(surname='Johnson', first_name='Mary').first()
        contacts = s.parent_contacts.all()
        assert len(contacts) == 1 and contacts[0].is_primary
        assert contacts[0].phone_number == '08099887766'   # leading 0 restored


def test_quoted_addresses_multi_phone_and_surname_only(app):
    """The real-world register paste: spaces before quotes, addresses with
    internal commas, two-phone cells, and a row with only a surname."""
    client = _admin(app)
    text = (
        'Surname, First Name, Middle Name, Gender, Date of Birth, Religion, Address, '
        'Hobbies, Name of Primary Contact, Phone Number, Relationship\n'
        'Emmanuel, Eliezer, Oghenemiro, , , Christianity, "No 64, Owie street Agbo Auchi Park", '
        ', Mrs. Emmanuel, 07038819942, Mother\n'
        'Ehigiatoc, Praise, Oseze-le, , , Christianity, "37 Omorogbe street, for-mer Road Eyean", '
        ', Mrs. Ehigiatoc, "08035341749, 07013850785", Mother\n'
        'Abdulrazak, , , , , Christianity, off Cherry road, , Mrs. Abdulrazak, 07066345619, Mother'
    )
    pre = _post(client, text=text).get_json()
    assert pre['ok'] and pre['valid'] == 3 and 'address' in pre['recognised']

    res = _post(client, text=text, commit='1').get_json()
    assert res['ok'] and res['created'] == 3
    with app.app_context():
        # internal-comma address survived intact (not split / shifted)
        em = Student.query.filter_by(surname='Emmanuel', first_name='Eliezer').first()
        assert em.home_address == 'No 64, Owie street Agbo Auchi Park'
        assert em.parent_contacts.first().relationship == 'Mother'
        # the two-phone cell became two contacts, first primary
        praise = Student.query.filter_by(surname='Ehigiatoc', first_name='Praise').first()
        phones = sorted(c.phone_number for c in praise.parent_contacts.all())
        assert phones == ['07013850785', '08035341749']
        assert praise.parent_contacts.filter_by(is_primary=True).count() == 1
        # surname-only row still imported (first name left blank)
        ab = Student.query.filter_by(surname='Abdulrazak').first()
        assert ab is not None and ab.first_name == ''


def test_overlong_values_are_capped_not_dropped(app):
    """An over-long value (e.g. a mis-shifted column dropping a long address
    into the 30-char religion field) must be truncated so the row still imports
    — on a length-enforcing DB (Postgres) it would otherwise roll back."""
    client = _admin(app)
    long_religion = 'A Very Long Religion Value That Exceeds Thirty Characters Easily'
    text = f'Surname, First Name, Religion\nCapped, Student, {long_religion}'
    res = _post(client, text=text, commit='1').get_json()
    assert res['ok'] and res['created'] == 1
    with app.app_context():
        s = Student.query.filter_by(surname='Capped', first_name='Student').first()
        assert s is not None and len(s.religion) == 30


def test_requires_a_name_column(app):
    client = _admin(app)
    r = _post(client, text='Phone, Religion\n08012345678, Islam')
    assert r.status_code == 400 and 'name column' in r.get_json()['error']


def test_empty_text_rejected(app):
    client = _admin(app)
    assert _post(client, text='   ').status_code == 400
    assert _post(client, text='Surname, First Name').status_code == 400  # header only


def test_import_exam_numbers_stream_target_and_subjects(app):
    client = _admin(app)
    text = ('Surname, First Name, Stream, JAMB Target, WAEC Subjects, JAMB Subjects, NIN, '
            'WAEC Reg Number, WAEC Serial Number, WAEC e-PIN, NECO Reg Number, NECO Token, '
            'JAMB Reg Number, JAMB Profile Code\n'
            'Zzexam, Necoimp, science, 260, English Language; Mathematics; Biology, '
            'Use of English; Biology; Chemistry; Physics, 12345678901, '
            'W111, S222, P333, N444, T555, J666, PC777\n'
            'Zzexam, Badvals, Engineering, 999, , , , , , , , , ,')
    pre = _post(client, text=text).get_json()
    assert pre['ok'] and pre['ignored'] == []
    for f in ('neco_reg_number', 'neco_epin', 'waec_reg_number', 'stream', 'jamb_target', 'waec_subjects'):
        assert f in pre['recognised'], f
    assert pre['rows'][0]['details']['neco_reg_number'] == 'N444'
    res = _post(client, text=text, commit='1').get_json()
    assert res['ok'] and res['created'] == 2
    assert any('stream' in m and 'Engineering'.lower() in m for m in res['messages'])
    assert any('JAMB target' in m for m in res['messages'])
    with app.app_context():
        s = Student.query.filter_by(surname='Zzexam', first_name='Necoimp').first()
        assert (s.neco_reg_number, s.neco_epin) == ('N444', 'T555')
        assert (s.waec_reg_number, s.serial_number, s.waec_epin) == ('W111', 'S222', 'P333')
        assert (s.jamb_reg_number, s.jamb_profile_code, s.nin) == ('J666', 'PC777', '12345678901')
        assert s.stream == 'Science' and s.jamb_target == 260
        assert s.waec_subjects == 'English Language, Mathematics, Biology'
        assert s.jamb_subjects == 'Use of English, Biology, Chemistry, Physics'
        bad = Student.query.filter_by(surname='Zzexam', first_name='Badvals').first()
        assert bad.stream is None and bad.jamb_target is None


def test_import_full_name_column(app):
    client = _admin(app)
    text = 'Full Name, Gender\nZZFULL Ngozi Adaeze, Female\n"Zzcomma, Emeka", Male'
    res = _post(client, text=text, commit='1').get_json()
    assert res['ok'] and res['created'] == 2
    with app.app_context():
        a = Student.query.filter_by(surname='ZZFULL').first()
        assert (a.first_name, a.middle_name) == ('Ngozi', 'Adaeze')
        b = Student.query.filter_by(surname='Zzcomma').first()
        assert b.first_name == 'Emeka'


def test_excel_template_has_exam_number_columns():
    from openpyxl import load_workbook
    from utils.excel_utils import create_student_import_template
    ws = load_workbook(create_student_import_template()).active
    heads = [c.value for c in ws[1]]
    for h in ('NECO Reg Number', 'WAEC Reg Number', 'JAMB Reg Number', 'NIN', 'Stream'):
        assert h in heads
