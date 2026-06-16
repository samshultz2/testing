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


def test_requires_a_name_column(app):
    client = _admin(app)
    r = _post(client, text='Phone, Religion\n08012345678, Islam')
    assert r.status_code == 400 and 'name column' in r.get_json()['error']


def test_empty_text_rejected(app):
    client = _admin(app)
    assert _post(client, text='   ').status_code == 400
    assert _post(client, text='Surname, First Name').status_code == 400  # header only
