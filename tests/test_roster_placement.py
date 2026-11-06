"""List-entered results place candidates in the exam's class for the exam
year's session: existing students outside it are moved in, unknown names are
added (Surname First Middle) — all behind one approval."""
import uuid

from config import Config
from models import (db, Student, WAECResult, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, StudentEnrollment)
from models.models_school_exams import SchoolExamResult
from tests.conftest import login_token, auth_csrf
from utils.roster_placement import split_name

YEAR = 2041                       # session "2040/2041" — not the live session


def test_split_name_surname_first_middle():
    assert split_name('John Okafor Mary') == ('John', 'Okafor', 'Mary')
    assert split_name('  ADA   obi ') == ('Ada', 'Obi', None)
    assert split_name('Bello Musa Ade Tunde') == ('Bello', 'Musa', 'Ade Tunde')
    assert split_name('Prince') is None


def _setup(app):
    """Session 2040/2041 (inactive, 2 terms) with arms for JSS2, JSS3, SSS2, SSS3
    in its last term. Returns {class name: assignment id}."""
    with app.app_context():
        ssn = AcademicSession.query.filter_by(name='2040/2041').first()
        if ssn is None:
            ssn = AcademicSession(name='2040/2041', is_active=False)
            db.session.add(ssn); db.session.flush()
            for n in (1, 2):
                db.session.add(Term(session_id=ssn.id, term_number=n, name=f'Term {n}', is_active=False))
            db.session.flush()
        term = Term.query.filter_by(session_id=ssn.id, term_number=2).first()
        arm = ClassArm.query.filter_by(name='Placement').first() or ClassArm(name='Placement', is_active=True)
        db.session.add(arm); db.session.flush()
        out = {}
        for cname, lvl in (('JSS2', 2), ('JSS3', 3), ('SSS2', 5), ('SSS3', 6)):
            cls = SchoolClass.query.filter_by(name=cname).first() or SchoolClass(name=cname, level=lvl)
            db.session.add(cls); db.session.flush()
            caa = (ClassArmAssignment.query.filter_by(class_id=cls.id, term_id=term.id).first()
                   or ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id))
            db.session.add(caa); db.session.flush()
            out[cname] = caa.id
        db.session.commit()
        return out


def _student_in(app, caa_id, first, surname):
    with app.app_context():
        s = Student(student_id='RP' + uuid.uuid4().hex[:6].upper(), first_name=first,
                    surname=surname, gender='Female')
        db.session.add(s); db.session.flush()
        db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa_id, is_active=True))
        db.session.commit()
        return s.id


def _admin(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    return c


def _active_classes(app, sid):
    with app.app_context():
        return {e.class_arm_assignment.school_class.name
                for e in StudentEnrollment.query.filter_by(student_id=sid, is_active=True)}


def test_jss3_quick_entry_moves_and_adds_after_one_approval(app):
    caas = _setup(app)
    sid = _student_in(app, caas['JSS2'], 'Kelechi', 'Rpmover')
    c = _admin(app)
    tok = auth_csrf(c)
    text = ('Rpmover Kelechi, Eng A, Maths B\n'
            'Rpnew Okafor Mary, English B, Maths C\n'
            'Rpskip Tunde, Eng P')
    data = {'_csrf_token': tok, 'year': YEAR, 'data': text}
    html = c.post('/jss3-exams/state/quick', data=dict(data, action='preview')).get_data(as_text=True)
    assert 'Needs your approval' in html and '2040/2041' in html
    assert 'Move into JSS3 (1)' in html and 'Add to the register (2)' in html

    # Saving without the approval tick changes nothing.
    c.post('/jss3-exams/state/quick', data=dict(data, action='confirm', inc=['1', '2', '3']))
    assert _active_classes(app, sid) == {'JSS2'}

    # Approve once; line 3 is unticked so it is skipped.
    r = c.post('/jss3-exams/state/quick', data=dict(data, action='confirm', approve_roster='1',
                                                    inc=['1', '2'], g_2='Female'))
    assert r.status_code == 302
    assert _active_classes(app, sid) == {'JSS3'}                 # moved, JSS2 deactivated
    with app.app_context():
        new = Student.query.filter_by(surname='Rpnew', first_name='Okafor').one()
        assert new.middle_name == 'Mary' and new.gender == 'Female' and new.student_id
        assert Student.query.filter_by(surname='Rpskip').count() == 0
        got = {(x.student_id, x.subject): x.grade for x in SchoolExamResult.query.filter_by(
            level='jss3', body='state', exam_year=YEAR)}
        assert got == {(sid, 'English Studies'): 'A', (sid, 'Mathematics'): 'B',
                       (new.id, 'English Studies'): 'B', (new.id, 'Mathematics'): 'C'}
    assert _active_classes(app, new.id) == {'JSS3'}

    # Entering again: both are now in JSS3, nothing needs approval.
    html = c.post('/jss3-exams/state/quick', data=dict(
        data, data='Rpmover Kelechi, Eng A\nRpnew Okafor Mary, Eng B', action='preview')).get_data(as_text=True)
    assert 'Needs your approval' not in html


def test_waec_quick_entry_moves_into_sss3(app):
    caas = _setup(app)
    sid = _student_in(app, caas['SSS2'], 'Adaeze', 'Rpwaec')
    c = _admin(app)
    tok = auth_csrf(c)
    data = {'_csrf_token': tok, 'year': YEAR, 'data': 'Rpwaec Adaeze, Eng A1, Maths B2\nRpwnew Chika Ada, Bio C4'}
    html = c.post('/results/waec/quick', data=dict(data, action='preview')).get_data(as_text=True)
    assert 'into SSS3' in html and 'Add to the register (1)' in html
    r = c.post('/results/waec/quick', data=dict(data, action='confirm', approve_roster='1', inc=['1', '2']))
    assert r.status_code == 302
    assert _active_classes(app, sid) == {'SSS3'}
    with app.app_context():
        new = Student.query.filter_by(surname='Rpwnew').one()
        assert (new.first_name, new.middle_name) == ('Chika', 'Ada')
        assert {w.subject: w.grade for w in WAECResult.query.filter_by(student_id=sid, exam_year=YEAR)} == {
            'English Language': 'A1', 'Mathematics': 'B2'}
        assert WAECResult.query.filter_by(student_id=new.id, exam_year=YEAR, subject='Biology').one().grade == 'C4'


def test_csv_import_adds_unknown_and_moves_by_student_id(app):
    caas = _setup(app)
    sid = _student_in(app, caas['JSS2'], 'Obinna', 'Rpcsv')
    with app.app_context():
        code = db.session.get(Student, sid).student_id
    c = _admin(app)
    tok = auth_csrf(c)
    text = ('Student ID,Name,Mathematics,English Studies\n'
            f'{code},,70,B\n'
            ',Rpcsvnew Ngozi,55,C\n')
    data = {'_csrf_token': tok, 'year': YEAR, 'data': text}
    html = c.post('/jss3-exams/federal/import', data=dict(data, action='preview')).get_data(as_text=True)
    assert 'Needs your approval' in html
    r = c.post('/jss3-exams/federal/import', data=dict(data, action='confirm', approve_roster='1',
                                                       inc=['2', '3']))
    assert r.status_code == 302
    assert _active_classes(app, sid) == {'JSS3'}
    with app.app_context():
        new = Student.query.filter_by(surname='Rpcsvnew', first_name='Ngozi').one()
        assert SchoolExamResult.query.filter_by(student_id=new.id, level='jss3', body='federal').count() == 2


def test_weak_match_defaults_to_new_but_can_use_existing(app):
    caas = _setup(app)
    bola = _student_in(app, caas['JSS3'], 'Bola', 'Zubairurp')       # already in JSS3
    c = _admin(app)
    tok = auth_csrf(c)
    data = {'_csrf_token': tok, 'year': YEAR, 'data': 'John Zubairurp Femi, Eng A\nZed Kwamerp Tom, Eng C'}
    html = c.post('/jss3-exams/state/quick', data=dict(data, action='preview')).get_data(as_text=True)
    assert "Yes — it&#39;s Zubairurp Bola" in html or "Yes — it's Zubairurp Bola" in html
    # Line 1: approver says it IS Bola; line 2 left at the default (new student).
    r = c.post('/jss3-exams/state/quick', data=dict(data, action='confirm', approve_roster='1',
                                                    inc=['1', '2'], use_1='existing'))
    assert r.status_code == 302
    with app.app_context():
        assert Student.query.filter_by(surname='John', first_name='Zubairurp').count() == 0
        assert SchoolExamResult.query.filter_by(student_id=bola, exam_year=YEAR,
                                                subject='English Studies').one().grade == 'A'
        zed = Student.query.filter_by(surname='Zed', first_name='Kwamerp').one()
        assert SchoolExamResult.query.filter_by(student_id=zed.id, exam_year=YEAR).one().grade == 'C'
    assert _active_classes(app, bola) == {'JSS3'}


# --------------------------------------------------------------------------- #
# WAEC paste page (one result slip) and Basic 6
# --------------------------------------------------------------------------- #
SLIP = "{name}\nEnglish Language, B3\nMathematics, C4"


def _paste(c, tok, name):
    return c.post('/results/waec/paste', data={'_csrf_token': tok, 'exam_year': YEAR,
                                               'data': SLIP.format(name=name)}).get_data(as_text=True)


def _save(c, tok, **extra):
    data = {'_csrf_token': tok, 'exam_year': YEAR,
            'subject[]': ['English Language', 'Mathematics'], 'grade[]': ['B3', 'C4']}
    data.update(extra)
    return c.post('/results/waec/paste/save', data=data)


def test_waec_paste_unknown_name_is_added_to_sss3_after_approval(app):
    _setup(app)
    c = _admin(app)
    tok = auth_csrf(c)
    html = _paste(c, tok, 'Pasteonly Chiamaka Grace')
    assert 'not on the register' in html and 'value="new" selected' in html
    assert 'value="Pasteonly"' in html and 'value="Chiamaka"' in html and 'value="Grace"' in html
    new = dict(student_id='new', new_surname='Pasteonly', new_first='Chiamaka', new_middle='Grace',
               new_gender='Female')
    _save(c, tok, **new)                                    # no approval tick → nothing
    with app.app_context():
        assert Student.query.filter_by(surname='Pasteonly').count() == 0
    r = _save(c, tok, approve_roster='1', **new)
    assert r.status_code == 302
    with app.app_context():
        st = Student.query.filter_by(surname='Pasteonly', first_name='Chiamaka').one()
        assert st.middle_name == 'Grace' and st.gender == 'Female'
        assert {w.subject: w.grade for w in WAECResult.query.filter_by(student_id=st.id, exam_year=YEAR)} == {
            'English Language': 'B3', 'Mathematics': 'C4'}
        sid = st.id
    assert _active_classes(app, sid) == {'SSS3'}


def test_waec_paste_moves_existing_student_into_sss3(app):
    caas = _setup(app)
    sid = _student_in(app, caas['SSS2'], 'Ifeanyi', 'Pastemover')
    c = _admin(app)
    tok = auth_csrf(c)
    html = _paste(c, tok, 'Pastemover Ifeanyi')
    assert 'moved into SSS3' in html and f'value="{sid}" selected data-roster="move"' in html
    _save(c, tok, student_id=str(sid))                      # no tick → refused, not moved
    assert _active_classes(app, sid) == {'SSS2'}
    with app.app_context():
        assert WAECResult.query.filter_by(student_id=sid, exam_year=YEAR).count() == 0
    r = _save(c, tok, student_id=str(sid), approve_roster='1')
    assert r.status_code == 302
    assert _active_classes(app, sid) == {'SSS3'}
    with app.app_context():
        assert WAECResult.query.filter_by(student_id=sid, exam_year=YEAR).count() == 2


def test_basic6_quick_entry_moves_and_adds(app):
    caas = _setup(app)
    with app.app_context():
        from models import Term
        ssn = AcademicSession.query.filter_by(name='2040/2041').one()
        term = Term.query.filter_by(session_id=ssn.id, term_number=2).one()
        arm = ClassArm.query.filter_by(name='Placement').one()
        out = {}
        for cname, lvl in (('Primary 5', 91), ('Primary 6', 90)):
            cls = SchoolClass.query.filter_by(name=cname).first() or SchoolClass(name=cname, level=lvl)
            db.session.add(cls); db.session.flush()
            caa = (ClassArmAssignment.query.filter_by(class_id=cls.id, term_id=term.id).first()
                   or ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id))
            db.session.add(caa); db.session.flush()
            out[cname] = caa.id
        db.session.commit()
    sid = _student_in(app, out['Primary 5'], 'Tobi', 'Basicmover')
    c = _admin(app)
    tok = auth_csrf(c)
    data = {'_csrf_token': tok, 'year': YEAR,
            'data': 'Basicmover Tobi, Eng A, QR B\nBasicnew Emeka Paul, Maths 81, VR C'}
    html = c.post('/basic6-exams/federal/quick', data=dict(data, action='preview')).get_data(as_text=True)
    assert 'Move into Basic 6 (1)' in html and 'Add to the register (1)' in html
    r = c.post('/basic6-exams/federal/quick', data=dict(data, action='confirm', approve_roster='1',
                                                        inc=['1', '2']))
    assert r.status_code == 302
    assert _active_classes(app, sid) == {'Primary 6'}
    with app.app_context():
        new = Student.query.filter_by(surname='Basicnew', first_name='Emeka').one()
        assert new.middle_name == 'Paul'
        got = {x.subject: x.grade for x in SchoolExamResult.query.filter_by(
            student_id=new.id, level='basic6', body='federal', exam_year=YEAR)}
        assert got == {'Mathematics': 'A', 'Verbal Reasoning': 'C'}
        new_id = new.id
    assert _active_classes(app, new_id) == {'Primary 6'}
