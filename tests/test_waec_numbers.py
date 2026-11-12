"""WAEC candidate numbers: 7-digit centre + 001… in surname order, per centre."""
from types import SimpleNamespace
from config import Config
from tests.conftest import login_token, auth_csrf


def _st(i, surname, first, num=None, branch=None):
    return SimpleNamespace(id=i, surname=surname, first_name=first, middle_name='', branch_id=branch,
                           waec_reg_number=num, student_id=f'S{i}', stream=None)


def test_clean_centre():
    from utils.waec_numbers import clean_centre
    assert clean_centre('4250101') == ('4250101', None)
    assert clean_centre(' 425 0101 ') == ('4250101', None)
    assert clean_centre('')[0] is None and clean_centre('')[1] is None
    assert clean_centre('12345')[1] and clean_centre('42501AB')[1]


def test_new_numbers_follow_surname_order_and_keep_existing(app):
    from utils import waec_numbers as wn
    from models import db, Branch
    with app.app_context():
        for b in Branch.query.all():
            b.waec_centre = None
        db.session.commit()
        wn.set_school_centre('4250101')
        try:
            studs = [_st(1, 'Okafor', 'Ada'), _st(2, 'Bello', 'Tunde'), _st(3, 'Bello', 'Amina'), _st(4, 'Eze', 'Chidi')]
            p = wn.plan(studs, 'fill')
            got = {r['student'].id: r['proposed'] for r in p['centres'][0]['rows']}
            # Bello Amina, Bello Tunde, Eze Chidi, Okafor Ada
            assert got == {3: '4250101001', 2: '4250101002', 4: '4250101003', 1: '4250101004'}
            # After registration a late candidate gets the next number; nobody else moves.
            for s in studs:
                s.waec_reg_number = got[s.id]
            late = _st(5, 'Adeyemi', 'Bisi')
            p2 = wn.plan(studs + [late], 'fill')
            rows = {r['student'].id: r for r in p2['centres'][0]['rows']}
            assert rows[5]['proposed'] == '4250101005' and rows[5]['status'] == 'new'
            assert all(rows[i]['status'] == 'keep' for i in (1, 2, 3, 4))
            # Renumbering puts the late candidate first and changes the others.
            p3 = wn.plan(studs + [late], 'renumber')
            rows3 = {r['student'].id: r for r in p3['centres'][0]['rows']}
            assert rows3[5]['proposed'] == '4250101001' and rows3[3]['status'] == 'change'
        finally:
            wn.set_school_centre('')


def test_each_branch_centre_numbers_from_001(app):
    from utils import waec_numbers as wn
    from models import db, Branch
    with app.app_context():
        a = Branch(name='WN Branch A', waec_centre='4250101')
        b = Branch(name='WN Branch B', waec_centre='4250202')
        db.session.add_all([a, b]); db.session.commit()
        try:
            studs = [_st(1, 'Zed', 'A', branch=a.id), _st(2, 'Ade', 'B', branch=b.id), _st(3, 'Bayo', 'C', branch=a.id)]
            p = wn.plan(studs, 'fill')
            nums = sorted(r['proposed'] for g in p['centres'] for r in g['rows'])
            assert nums == ['4250101001', '4250101002', '4250202001']
        finally:
            db.session.delete(a); db.session.delete(b); db.session.commit()


def test_page_saves_centres_and_numbers(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    page = c.get('/settings/waec-numbers').get_data(as_text=True)
    assert 'WAEC candidate numbers' in page and '10 digits' in page
    r = c.post('/settings/waec-numbers', data={'_csrf_token': auth_csrf(c), 'action': 'centres', 'school_centre': '12'})
    assert r.status_code in (302, 303)
    from utils import waec_numbers as wn
    with app.app_context():
        assert wn.school_centre() is None                      # invalid number refused
    c.post('/settings/waec-numbers', data={'_csrf_token': auth_csrf(c), 'action': 'centres', 'school_centre': '4250101'})
    with app.app_context():
        assert wn.school_centre() == '4250101'
        wn.set_school_centre('')


def _stn(i, surname, first, neco=None, branch=None):
    s = _st(i, surname, first, branch=branch)
    s.neco_reg_number = neco
    return s


def test_school_without_branches_uses_the_school_number(app, monkeypatch):
    """No branches at all: every candidate is numbered under the school-wide centre."""
    from utils import waec_numbers as wn
    monkeypatch.setattr(wn, '_branch_map', lambda: {})
    with app.app_context():
        wn.set_school_centre('4250101')
        try:
            p = wn.plan([_st(1, 'Musa', 'A'), _st(2, 'Ade', 'B')], 'fill')
            assert len(p['centres']) == 1 and p['centres'][0]['label'] == 'Whole school'
            assert [r['proposed'] for r in p['centres'][0]['rows']] == ['4250101001', '4250101002']
            assert not p['missing']
        finally:
            wn.set_school_centre('')
        # And with no number set, nobody can be numbered — they're listed instead.
        p = wn.plan([_st(1, 'Musa', 'A')], 'fill')
        assert p['centres'] == [] and len(p['missing']) == 1


def test_single_branch_school_is_labelled_whole_school(app, monkeypatch):
    from utils import waec_numbers as wn
    only = SimpleNamespace(id=1, name='Main', is_default=True, waec_centre=None, neco_centre=None)
    monkeypatch.setattr(wn, '_branch_map', lambda: {1: only})
    with app.app_context():
        wn.set_school_centre('4250101')
        try:
            p = wn.plan([_st(1, 'Musa', 'A', branch=1), _st(2, 'Ade', 'B', branch=None)], 'fill')
            assert p['centres'][0]['label'] == 'Whole school' and len(p['centres'][0]['rows']) == 2
        finally:
            wn.set_school_centre('')


def test_neco_numbers_are_separate_from_waec(app, monkeypatch):
    from utils import waec_numbers as wn
    monkeypatch.setattr(wn, '_branch_map', lambda: {})
    assert wn.clean_centre('12', 'neco')[1] and wn.clean_centre('ab12cd', 'neco') == ('AB12CD', None)
    with app.app_context():
        wn.set_school_centre('4250101')
        wn.set_school_centre('7712345', 'neco')
        try:
            studs = [_stn(1, 'Okafor', 'Ada'), _stn(2, 'Bello', 'Tunde', neco='7712345001')]
            p = wn.plan(studs, 'fill', 'neco')
            rows = {r['student'].id: r for r in p['centres'][0]['rows']}
            assert rows[2]['status'] == 'keep' and rows[1]['proposed'] == '7712345002'
            # WAEC numbering of the same students is independent.
            pw = wn.plan(studs, 'fill', 'waec')
            assert {r['proposed'] for r in pw['centres'][0]['rows']} == {'4250101001', '4250101002'}
        finally:
            wn.set_school_centre('')
            wn.set_school_centre('', 'neco')


def test_neco_tab_saves_its_own_centre(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    page = c.get('/settings/waec-numbers?board=neco').get_data(as_text=True)
    assert 'NECO candidate numbers' in page
    c.post('/settings/waec-numbers', data={'_csrf_token': auth_csrf(c), 'action': 'centres', 'board': 'neco',
                                          'school_centre': '7712345'})
    from utils import waec_numbers as wn
    with app.app_context():
        assert wn.school_centre('neco') == '7712345' and wn.school_centre('waec') is None
        wn.set_school_centre('', 'neco')
