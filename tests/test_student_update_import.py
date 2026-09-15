"""Paste-to-update students: match pasted rows against existing students,
scoped to one class (and optionally one arm) so the search never scans the
whole school, then apply only the fields a row actually supplies — preview
first, commit second, same two-step pattern as the add importer."""
import re

from config import Config
from models import (
    db, Student, ParentContact, AcademicSession, Term, SchoolClass, ClassArm,
    ClassArmAssignment, StudentEnrollment,
)
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
    return client.post('/students/update-import', headers={'X-Requested-With': 'fetch'}, data=data)


def _setup_class_arm(app, tag, students):
    """One class + arm (unique per test) enrolled for the active term, with
    the given [(surname, first_name), ...] students created and enrolled.
    Returns (class_id, arm_id, [(db_id, student_code), ...] in creation order).
    A list (not a name-keyed dict) so two same-named students — deliberately
    used by the ambiguous-match tests — don't collide with each other, or
    with same-named students another test in this shared-DB session created."""
    with app.app_context():
        # Use the exact same lookup the route itself uses (get_active_term()) —
        # querying Term.is_active directly can disagree with it when another
        # test in this shared-DB session left an active term whose session_id
        # doesn't match the active session (get_active_term() then falls back
        # to that session's own current term instead).
        from utils.helpers import get_active_term
        term = get_active_term()
        if term is None:
            ssn = AcademicSession(name='ZzENR', is_active=True)
            db.session.add(ssn); db.session.flush()
            term = Term(session_id=ssn.id, term_number=1, name='ZzTerm', is_active=True)
            db.session.add(term); db.session.flush()
            db.session.commit()
            term = get_active_term()
            assert term is not None

        sc = SchoolClass(name=f'ZzUpd{tag}', level=1)
        arm = ClassArm(name=f'ZzArm{tag}', is_active=True)
        db.session.add_all([sc, arm]); db.session.flush()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id)
        db.session.add(caa); db.session.flush()

        created = []
        for surname, first_name in students:
            s = Student(student_id=Student.generate_student_id(), surname=surname,
                       first_name=first_name, gender='Male', is_active=True)
            db.session.add(s); db.session.flush()
            db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id,
                                             is_active=True))
            created.append((s.id, s.student_id))
        db.session.commit()
        return sc.id, arm.id, created


def test_requires_class_id(app):
    client = _admin(app)
    r = _post(client, text='Surname, First Name\nZzOkafor, ZzChidi')
    assert r.status_code == 400 and 'class' in r.get_json()['error'].lower()


def test_update_by_name_within_scoped_class_arm(app):
    class_id, arm_id, codes = _setup_class_arm(app, 'A', [('ZzOkafor', 'ZzChidi')])
    client = _admin(app)

    text = 'Surname, First Name, Religion\nZzOkafor, ZzChidi, Islam'
    pre = _post(client, text=text, class_id=class_id, arm_id=arm_id).get_json()
    assert pre['ok'] and pre['preview'] is True and pre['matched'] == 1
    row = pre['rows'][0]
    assert row['matched'] and row['name'] == 'ZzOkafor ZzChidi'
    assert {'field': 'religion', 'label': 'Religion', 'old': None, 'new': 'Islam'} in row['changes']

    # Preview must not have written anything.
    with app.app_context():
        assert Student.query.get(codes[0][0]).religion is None

    res = _post(client, text=text, class_id=class_id, arm_id=arm_id, commit='1').get_json()
    assert res['ok'] and res['updated'] == 1
    with app.app_context():
        assert Student.query.get(codes[0][0]).religion == 'Islam'


def test_does_not_touch_same_named_student_in_a_different_class(app):
    """The whole point of scoping: a same-named student who is NOT enrolled in
    the chosen class/arm must be left alone, not silently matched from the
    rest of the database."""
    class_id, arm_id, codes = _setup_class_arm(app, 'B', [('ZzBello', 'ZzMusa')])
    # A different, unrelated 'ZzBello ZzMusa' elsewhere (no class enrolment at all).
    with app.app_context():
        other = Student(student_id=Student.generate_student_id(), surname='ZzBello',
                        first_name='ZzMusa', gender='Male', is_active=True, religion='Christianity')
        db.session.add(other); db.session.commit()
        other_id = other.id

    client = _admin(app)
    text = 'Surname, First Name, Religion\nZzBello, ZzMusa, Islam'
    res = _post(client, text=text, class_id=class_id, arm_id=arm_id, commit='1').get_json()
    assert res['ok'] and res['updated'] == 1
    with app.app_context():
        assert Student.query.get(codes[0][0]).religion == 'Islam'
        assert Student.query.get(other_id).religion == 'Christianity'   # untouched


def test_ambiguous_name_requires_student_id(app):
    class_id, arm_id, codes = _setup_class_arm(app, 'C', [('ZzAdeyemi', 'ZzTunde'), ('ZzAdeyemi', 'ZzTunde')])
    client = _admin(app)
    text = 'Surname, First Name, Religion\nZzAdeyemi, ZzTunde, Islam'
    pre = _post(client, text=text, class_id=class_id, arm_id=arm_id).get_json()
    assert pre['ok']
    row = pre['rows'][0]
    assert row['matched'] is False and 'Student ID' in row['error']

    res = _post(client, text=text, class_id=class_id, arm_id=arm_id, commit='1').get_json()
    assert res['ok'] and res['updated'] == 0
    assert any('Student ID' in m for m in res['messages'])


def test_match_by_student_id_disambiguates(app):
    class_id, arm_id, codes = _setup_class_arm(app, 'D', [('ZzAdeyemi', 'ZzTunde'), ('ZzAdeyemi', 'ZzTunde')])
    (id_a, code_a), (id_b, _code_b) = codes

    client = _admin(app)
    text = f'Student ID, Surname, First Name, Religion\n{code_a}, ZzAdeyemi, ZzTunde, Islam'
    res = _post(client, text=text, class_id=class_id, arm_id=arm_id, commit='1').get_json()
    assert res['ok'] and res['updated'] == 1
    with app.app_context():
        assert Student.query.get(id_a).religion == 'Islam'
        assert Student.query.get(id_b).religion is None   # the other one untouched


def test_not_found_in_scope_is_reported_not_silently_dropped(app):
    class_id, arm_id, codes = _setup_class_arm(app, 'E', [('ZzOkafor', 'ZzChidi')])
    client = _admin(app)
    text = 'Surname, First Name\nNonexistent, Person'
    pre = _post(client, text=text, class_id=class_id, arm_id=arm_id).get_json()
    assert pre['ok']
    row = pre['rows'][0]
    assert row['matched'] is False and 'not found' in row['error'].lower()


def test_blank_cell_leaves_existing_value_unchanged(app):
    class_id, arm_id, codes = _setup_class_arm(app, 'F', [('ZzOkafor', 'ZzChidi')])
    with app.app_context():
        s = Student.query.get(codes[0][0])
        s.religion = 'Christianity'
        s.middle_name = 'Emeka'
        db.session.commit()

    client = _admin(app)
    # Religion column present but blank for this row, Middle Name omitted entirely.
    text = 'Surname, First Name, Religion, Hobbies\nZzOkafor, ZzChidi, , Football'
    res = _post(client, text=text, class_id=class_id, arm_id=arm_id, commit='1').get_json()
    assert res['ok'] and res['updated'] == 1
    with app.app_context():
        s = Student.query.get(codes[0][0])
        assert s.religion == 'Christianity'   # blank cell -> untouched
        assert s.middle_name == 'Emeka'        # column not even pasted -> untouched
        assert s.hobbies == 'Football'         # actually supplied -> updated


def test_no_op_row_reports_no_changes_and_does_not_count_as_updated(app):
    class_id, arm_id, codes = _setup_class_arm(app, 'G', [('ZzOkafor', 'ZzChidi')])
    with app.app_context():
        s = Student.query.get(codes[0][0])
        s.religion = 'Islam'
        db.session.commit()

    client = _admin(app)
    text = 'Surname, First Name, Religion\nZzOkafor, ZzChidi, Islam'
    pre = _post(client, text=text, class_id=class_id, arm_id=arm_id).get_json()
    assert pre['rows'][0]['no_changes'] is True

    res = _post(client, text=text, class_id=class_id, arm_id=arm_id, commit='1').get_json()
    assert res['ok'] and res['updated'] == 0


def test_phone_must_be_exactly_11_digits(app):
    class_id, arm_id, codes = _setup_class_arm(app, 'H', [('ZzOkafor', 'ZzChidi')])
    client = _admin(app)
    text = 'Surname, First Name, Father Phone\nZzOkafor, ZzChidi, 12345'
    pre = _post(client, text=text, class_id=class_id, arm_id=arm_id).get_json()
    row = pre['rows'][0]
    assert row['matched'] and row['contact_changes'] == []
    assert row['warn'] and '12345' in row['warn']

    res = _post(client, text=text, class_id=class_id, arm_id=arm_id, commit='1').get_json()
    assert res['ok']
    assert any('11 digits' in m for m in res['messages'])
    with app.app_context():
        s = Student.query.get(codes[0][0])
        assert s.parent_contacts.count() == 0   # bad number never saved


def test_mother_and_father_phones_create_two_distinct_contacts(app):
    class_id, arm_id, codes = _setup_class_arm(app, 'I', [('ZzOkafor', 'ZzChidi')])
    client = _admin(app)
    text = ('Surname, First Name, Father Name, Father Phone, Mother Name, Mother Phone\n'
            'ZzOkafor, ZzChidi, Mr. ZzOkafor, 08011112222, Mrs. ZzOkafor, 08033334444')
    res = _post(client, text=text, class_id=class_id, arm_id=arm_id, commit='1').get_json()
    assert res['ok'] and res['updated'] == 1
    with app.app_context():
        s = Student.query.get(codes[0][0])
        contacts = {c.relationship: c for c in s.parent_contacts.all()}
        assert contacts['Father'].phone_number == '08011112222'
        assert contacts['Father'].name == 'Mr. ZzOkafor'
        assert contacts['Mother'].phone_number == '08033334444'
        assert contacts['Mother'].name == 'Mrs. ZzOkafor'
        assert sum(1 for c in contacts.values() if c.is_primary) == 1

    # Re-pasting with just an updated father phone must upsert (not duplicate)
    # the Father contact and leave Mother's alone.
    text2 = 'Surname, First Name, Father Phone\nZzOkafor, ZzChidi, 08099998888'
    res2 = _post(client, text=text2, class_id=class_id, arm_id=arm_id, commit='1').get_json()
    assert res2['ok'] and res2['updated'] == 1
    with app.app_context():
        s = Student.query.get(codes[0][0])
        assert s.parent_contacts.count() == 2   # still two, not three
        contacts = {c.relationship: c for c in s.parent_contacts.all()}
        assert contacts['Father'].phone_number == '08099998888'
        assert contacts['Mother'].phone_number == '08033334444'   # untouched


def test_arm_scoping_excludes_students_in_other_arms_of_same_class(app):
    with app.app_context():
        from utils.helpers import get_active_term
        term = get_active_term()
        if term is None:
            ssn = AcademicSession(name='ZzENR', is_active=True)
            db.session.add(ssn); db.session.flush()
            term = Term(session_id=ssn.id, term_number=1, name='ZzTerm', is_active=True)
            db.session.add(term); db.session.flush()
            db.session.commit()
            term = get_active_term()
            assert term is not None

        sc = SchoolClass(name='ZzUpdJ', level=1)
        arm1 = ClassArm(name='ZzArmJ1', is_active=True)
        arm2 = ClassArm(name='ZzArmJ2', is_active=True)
        db.session.add_all([sc, arm1, arm2]); db.session.flush()
        caa1 = ClassArmAssignment(class_id=sc.id, arm_id=arm1.id, term_id=term.id)
        caa2 = ClassArmAssignment(class_id=sc.id, arm_id=arm2.id, term_id=term.id)
        db.session.add_all([caa1, caa2]); db.session.flush()

        s1 = Student(student_id=Student.generate_student_id(), surname='ZzOkoro',
                    first_name='ZzAda', gender='Female', is_active=True)
        db.session.add(s1); db.session.flush()
        s2 = Student(student_id=Student.generate_student_id(), surname='ZzOkoro',
                    first_name='ZzAda', gender='Female', is_active=True)
        db.session.add(s2); db.session.flush()
        db.session.add(StudentEnrollment(student_id=s1.id, class_arm_assignment_id=caa1.id, is_active=True))
        db.session.add(StudentEnrollment(student_id=s2.id, class_arm_assignment_id=caa2.id, is_active=True))
        db.session.commit()
        class_id, arm1_id, s1_id, s2_id = sc.id, arm1.id, s1.id, s2.id

    client = _admin(app)
    text = 'Surname, First Name, Religion\nZzOkoro, ZzAda, Islam'
    # Scoped to arm1 only — the same name in arm2 is a different student and
    # must not create an ambiguous-match error, since it's outside scope.
    res = _post(client, text=text, class_id=class_id, arm_id=arm1_id, commit='1').get_json()
    assert res['ok'] and res['updated'] == 1
    with app.app_context():
        assert Student.query.get(s1_id).religion == 'Islam'
        assert Student.query.get(s2_id).religion is None
