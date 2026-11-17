"""Results import (/results/import): preview first, then save only the rows
that pass — grades checked, students matched only inside the user's branch."""
import uuid

from models import db, Branch, JAMBResult, NECOResult, Student, WAECResult
from tests.test_medical_access import _admin, _csrf

H = {'X-Requested-With': 'fetch'}


def _seed(app):
    tag = uuid.uuid4().hex[:5].upper()
    with app.app_context():
        bid = Branch.get_default().id
        other = Branch(name=f'ZzImpOther{tag}', code=None); db.session.add(other); db.session.flush()
        a = Student(student_id=f'IM{tag}A', first_name='Ada', surname=f'Zimp{tag}', gender='Female', is_active=True, branch_id=bid)
        b = Student(student_id=f'IM{tag}B', first_name='Bayo', surname=f'Zimp{tag}', gender='Male', is_active=True, branch_id=bid)
        x = Student(student_id=f'IM{tag}X', first_name='Xeno', surname=f'Zimp{tag}', gender='Male', is_active=True, branch_id=other.id)
        db.session.add_all([a, b, x]); db.session.commit()
        return tag, a.id, b.id, x.id


def _post(c, exam, text, mode, year=2026):
    return c.post(f'/results/import/{exam}', headers=H,
                  data={'_csrf_token': _csrf(c), 'text': text, 'mode': mode, 'year': str(year)})


def test_preview_saves_nothing_and_flags_each_problem(app):
    tag, a, b, x = _seed(app)
    c = _admin(app)
    sheet = ('student_id,exam_year,subject,grade\n'
             f'IM{tag}A,2026,Mathematics,B2\n'
             f'IM{tag}A,2026,English Language,Z9\n'        # not a grade
             f'NOPE{tag},2026,Biology,C4\n'                  # unknown student
             f'IM{tag}B,2026,Maths,c5\n')                    # alias + lower case is fine
    d = _post(c, 'waec', sheet, 'preview').get_json()
    assert d['ok'] and d['layout'] == 'long'
    st = {r['line']: r for r in d['rows']}
    assert st[2]['status'] == 'new' and st[5]['status'] == 'new'
    assert st[5]['items'][0] == {'subject': 'Mathematics', 'value': 'C5'}
    assert st[3]['status'] == 'error' and 'not a grade' in st[3]['problems'][0]
    assert st[4]['status'] == 'error' and 'No student' in st[4]['problems'][0]
    with app.app_context():
        assert WAECResult.query.filter(WAECResult.student_id.in_([a, b])).count() == 0


def test_apply_saves_only_the_good_rows_and_updates_on_reimport(app):
    tag, a, b, x = _seed(app)
    c = _admin(app)
    sheet = ('student_id,exam_year,subject,grade\n'
             f'IM{tag}A,2026,Mathematics,B2\n'
             f'IM{tag}A,2026,English Language,Z9\n'
             f'IM{tag}B,2026,Biology,A1\n')
    d = _post(c, 'waec', sheet, 'apply').get_json()
    assert d['ok'] and d['added'] == 2 and d['updated'] == 0 and d['skipped'] == 1
    with app.app_context():
        assert {(r.student_id, r.subject, r.grade) for r in WAECResult.query.filter(WAECResult.student_id.in_([a, b]))} == {
            (a, 'Mathematics', 'B2'), (b, 'Biology', 'A1')}
    d2 = _post(c, 'waec', f'student_id,exam_year,subject,grade\nIM{tag}A,2026,Mathematics,C4\n', 'apply').get_json()
    assert d2['updated'] == 1 and d2['added'] == 0
    with app.app_context():
        assert WAECResult.query.filter_by(student_id=a, subject='Mathematics').one().grade == 'C4'


def test_other_branch_students_are_never_matched(app):
    tag, a, b, x = _seed(app)
    with app.app_context():
        bid = Branch.get_default().id
    c = _admin(app)
    with c.session_transaction() as s:
        s['view_branch_id'] = bid
    d = _post(c, 'waec', f'student_id,exam_year,subject,grade\nIM{tag}X,2026,Mathematics,B2\n', 'apply').get_json()
    assert d['added'] == 0 and d['skipped'] == 1
    with app.app_context():
        assert WAECResult.query.filter_by(student_id=x).count() == 0


def test_one_row_per_student_layout_and_neco(app):
    tag, a, b, x = _seed(app)
    c = _admin(app)
    sheet = ('Admission No\tYear\tEnglish Language\tMathematics\tBiology\tRemarks\n'
             f'IM{tag}A\t2025/2026\tC4\tB3\tABS\tGood\n')
    d = _post(c, 'neco', sheet, 'preview').get_json()
    assert d['layout'] == 'wide'
    r = d['rows'][0]
    assert r['status'] == 'new' and r['year'] == 2026
    assert [(i['subject'], i['value']) for i in r['items']] == [('English Language', 'C4'), ('Mathematics', 'B3')]
    assert any('absent' in n for n in r['notes'])
    assert _post(c, 'neco', sheet, 'apply').get_json()['added'] == 2
    with app.app_context():
        assert NECOResult.query.filter_by(student_id=a).count() == 2
        assert WAECResult.query.filter_by(student_id=a).count() == 0


def test_same_subject_twice_with_different_grades_is_a_problem(app):
    tag, a, b, x = _seed(app)
    c = _admin(app)
    sheet = ('student_id,exam_year,subject,grade\n'
             f'IM{tag}A,2026,Mathematics,B2\n'
             f'IM{tag}A,2026,Mathematics,C6\n')
    rows = _post(c, 'waec', sheet, 'preview').get_json()['rows']
    assert rows[0]['status'] == 'new' and rows[1]['status'] == 'error'
    assert 'row 2' in rows[1]['problems'][0]


def test_jamb_checks_scores_and_adds_up_a_missing_total(app):
    tag, a, b, x = _seed(app)
    c = _admin(app)
    sheet = ('student_id,exam_year,total_score,subject1,subject1_score,subject2,subject2_score,subject3,subject3_score,subject4,subject4_score\n'
             f'IM{tag}A,2026,,English Language,60,Mathematics,70,Physics,55,Chemistry,65\n'
             f'IM{tag}B,2026,450,English Language,60,,,,,,\n'
             f'IM{tag}B,2026,200,English Language,160,,,,,,\n')
    rows = _post(c, 'jamb', sheet, 'preview').get_json()['rows']
    assert rows[0]['status'] == 'new' and rows[0]['total'] == 250
    assert 'not between 0 and 400' in rows[1]['problems'][0]
    assert 'not between 0 and 100' in rows[2]['problems'][0]
    assert _post(c, 'jamb', sheet, 'apply').get_json()['added'] == 1
    with app.app_context():
        j = JAMBResult.query.filter_by(student_id=a).one()
        assert j.total_score == 250 and j.subject2 == 'Mathematics' and j.subject2_score == 70


def test_unreadable_sheet_says_why(app):
    c = _admin(app)
    r = _post(c, 'waec', '', 'preview')
    assert r.status_code == 400 and r.get_json()['error']


def test_preview_shows_the_grade_an_update_replaces(app):
    tag, a, b, x = _seed(app)
    c = _admin(app)
    _post(c, 'waec', f'student_id,exam_year,subject,grade\nIM{tag}A,2026,Mathematics,C4\n', 'apply')
    row = _post(c, 'waec', f'student_id,exam_year,subject,grade\nIM{tag}A,2026,Mathematics,B2\n', 'preview').get_json()['rows'][0]
    assert row['status'] == 'update' and row['items'][0] == {'subject': 'Mathematics', 'value': 'B2', 'was': 'C4'}
