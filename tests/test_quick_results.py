"""Quick "one line per candidate" entry: ``Name, Eng A1, Maths B2`` for WAEC
(A1 … F9) and ``Name, Eng A, Maths B`` for JSS3 / Basic 6 (plain letters)."""
import uuid

from config import Config
from models import db, Student, WAECResult
from models.models_school_exams import ExamScheme, SchoolExamResult
from tests.conftest import login_token, auth_csrf, enroll_sss3
from utils.quick_results import (parse_quick_lines, waec_spec, school_exam_spec,
                                 make_subject_resolver, _split_field)


class _S:
    def __init__(self, i, first, surname, middle=None):
        self.id, self.first_name, self.surname, self.middle_name = i, first, surname, middle
        self.student_id = f'S{i}'

    @property
    def full_name(self):
        return ' '.join(x for x in (self.surname, self.first_name, self.middle_name) if x)


ROSTER = [_S(1, 'John', 'Matthew', 'Caleb'), _S(2, 'Ada', 'Obi'), _S(3, 'Musa', 'Bello')]


def test_split_field_forms():
    assert _split_field('Eng A1') == ('Eng', 'A1')
    assert _split_field('Eng: A1') == ('Eng', 'A1')
    assert _split_field('Basic Science - B') == ('Basic Science', 'B')
    assert _split_field('Maths=72') == ('Maths', '72')
    assert _split_field('English') == (None, None)


def test_waec_lines_parse_and_match():
    out = parse_quick_lines('John Caleb Matthew, Eng A1, Maths B2, Bio c4\n'
                            'Obi Ada, English Language C6; F. Maths A1\n', ROSTER, waec_spec())
    r1, r2 = out['rows']
    assert r1['student'].id == 1 and not r1['errors']
    assert [(s, g) for s, _sc, g, _ in r1['items']] == [
        ('English Language', 'A1'), ('Mathematics', 'B2'), ('Biology', 'C4')]
    assert r2['student'].id == 2
    assert {s for s, *_ in r2['items']} == {'English Language', 'Further Mathematics'}
    assert out['n_ready'] == 2 and out['n_results'] == 5


def test_waec_rejects_plain_letters_and_unknowns():
    out = parse_quick_lines('Musa Bello, Eng A, Maths 70, Basket Weaving A1\n'
                            'Nobody Here, Eng A1', ROSTER, waec_spec())
    r1, r2 = out['rows']
    assert r1['items'] == []
    msgs = ' '.join(r1['errors'])
    assert 'not a WAEC grade' in msgs and 'not scores' in msgs and 'Basket Weaving' in msgs
    assert r2['student'] is None and 'No SSS3 / WAEC candidate matches' in r2['errors'][0]
    assert out['n_ready'] == 0


def test_school_exam_letters_scores_and_waec_style_rejected():
    sc = ExamScheme('jss3', 'state')
    out = parse_quick_lines('John Caleb Matthew, Eng A, Maths B2, Basic Sci C, BTech 45, CCA p, '
                            'CRS f, SOS Z', ROSTER, school_exam_spec(sc, 'JSS3'))
    r = out['rows'][0]
    got = {s: (score, g) for s, score, g, _ in r['items']}
    assert got == {'English Studies': (None, 'A'), 'Basic Science': (None, 'C'),
                   'Basic Technology': (45.0, 'P'), 'Cultural and Creative Arts': (None, 'P'),
                   'Christian Religious Studies': (None, 'F')}
    msgs = ' '.join(r['errors'])
    assert 'WAEC-style grade' in msgs and 'B2' in msgs          # Maths B2 refused
    assert '"Z" is not a State BECE grade' in msgs


def test_neco_bece_has_no_b_grade():
    sc = ExamScheme('jss3', 'federal')                           # A / C / P / F
    r = parse_quick_lines('Ada Obi, Eng B, Maths C', ROSTER, school_exam_spec(sc, 'JSS3'))['rows'][0]
    assert [(s, g) for s, _x, g, _ in r['items']] == [('Mathematics', 'C')]
    assert 'NECO BECE grade' in r['errors'][0]


def test_basic6_subject_shortcuts():
    sc = ExamScheme('basic6', 'federal')
    res = make_subject_resolver(sc.subjects)
    assert res('BST') == 'Basic Science and Technology'
    assert res('QR') == 'Quantitative Reasoning'
    assert res('verbal') == 'Verbal Reasoning'
    assert res('Eng') == 'English Studies'
    assert res('Physics') is None


# --------------------------------------------------------------------------- #
# Through the pages
# --------------------------------------------------------------------------- #
def _admin(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    return c


def _student(app, first, surname, middle=None):
    with app.app_context():
        s = Student(student_id='QE' + uuid.uuid4().hex[:6].upper(), first_name=first,
                    middle_name=middle, surname=surname, gender='Male')
        db.session.add(s)
        db.session.commit()
        return s.id


def test_waec_quick_entry_saves(app):
    sid = _student(app, 'Calebqe', 'Matthewqe', 'Johnqe')
    enroll_sss3(app, sid)
    c = _admin(app)
    tok = auth_csrf(c)
    text = 'Johnqe Calebqe Matthewqe, Eng A1, Maths B2'
    assert c.get('/results/waec/quick').status_code == 200
    html = c.post('/results/waec/quick', data={'_csrf_token': tok, 'year': 2031, 'data': text,
                                               'action': 'preview'}).get_data(as_text=True)
    assert 'Matthewqe Calebqe Johnqe' in html and 'Save 2 result(s) for 1 candidate(s)' in html
    r = c.post('/results/waec/quick', data={'_csrf_token': tok, 'year': 2031, 'data': text,
                                            'action': 'confirm'})
    assert r.status_code == 302
    with app.app_context():
        got = {w.subject: w.grade for w in WAECResult.query.filter_by(student_id=sid, exam_year=2031)}
        assert got == {'English Language': 'A1', 'Mathematics': 'B2'}


def test_jss3_and_basic6_quick_entry_save(app):
    from tests.test_school_exams import _enroll
    j = _student(app, 'Jqe', 'Okeqe')
    b = _student(app, 'Bqe', 'Ibeqe')
    _enroll(app, 'JSS3', 3, j)
    _enroll(app, 'Primary 6', 90, b)
    c = _admin(app)
    tok = auth_csrf(c)
    for level, body, line, want in (
            ('jss3', 'state', 'Jqe Okeqe, Eng A, Maths B, Basic Science 48',
             {'English Studies': 'A', 'Mathematics': 'B', 'Basic Science': 'P'}),
            ('basic6', 'federal', 'Ibeqe Bqe, English A, QR C, Maths 81',
             {'English Studies': 'A', 'Quantitative Reasoning': 'C', 'Mathematics': 'A'})):
        assert c.get(f'/{level}-exams/{body}/quick').status_code == 200
        r = c.post(f'/{level}-exams/{body}/quick', data={
            '_csrf_token': tok, 'year': 2031, 'data': line, 'action': 'confirm'})
        assert r.status_code == 302, level
        sid = j if level == 'jss3' else b
        with app.app_context():
            got = {x.subject: x.grade for x in SchoolExamResult.query.filter_by(
                student_id=sid, level=level, body=body, exam_year=2031)}
        assert got == want, level
