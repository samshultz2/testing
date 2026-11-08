"""Class setup groups arms per class with boys/girls counts, and the class
roster carries the surname / gender data its A–Z and by-gender views sort on,
plus the class's other arms for switching."""
import json
import re
import uuid

from config import Config
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment)
from tests.conftest import login_token


def _payload(html):
    m = re.search(r'<script type="application/json" id="acad-data">(.*?)</script>', html, re.S)
    return json.loads(m.group(1))


def test_class_tabs_counts_and_roster_sort_fields(app):
    tag = uuid.uuid4().hex[:5].upper()
    with app.app_context():
        bid = Branch.get_default().id
        sess = AcademicSession(name='CST-' + tag); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='CST-T-' + tag); db.session.add(term); db.session.flush()
        sc = SchoolClass(name='CST' + tag, level=900, is_active=True); db.session.add(sc)
        a1 = ClassArm(name='Ax' + tag, is_active=True); a2 = ClassArm(name='Bx' + tag, is_active=True)
        db.session.add_all([a1, a2]); db.session.flush()
        c1 = ClassArmAssignment(class_id=sc.id, arm_id=a1.id, term_id=term.id, branch_id=bid, form_teacher_name='Mrs Ojo')
        c2 = ClassArmAssignment(class_id=sc.id, arm_id=a2.id, term_id=term.id, branch_id=bid)
        db.session.add_all([c1, c2]); db.session.flush()
        for i, (sn, fn, g) in enumerate([('Zubair', 'Ali', 'Male'), ('Adamu', 'Bola', 'Female'), ('Musa', 'Chi', 'Male')]):
            s = Student(student_id=f'CS{tag}{i}', first_name=fn, surname=sn, gender=g, is_active=True, branch_id=bid)
            db.session.add(s); db.session.flush()
            db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=c1.id, is_active=True))
        db.session.commit()
        term_id, c1_id, c2_id, class_id = term.id, c1.id, c2.id, sc.id

    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    d = _payload(c.get(f'/academics/assignments?term_id={term_id}').get_data(as_text=True))
    mine = {a['id']: a for a in d['assignments'] if a['class_id'] == class_id}
    assert set(mine) == {c1_id, c2_id}
    assert (mine[c1_id]['students'], mine[c1_id]['boys'], mine[c1_id]['girls']) == (3, 2, 1)
    assert mine[c1_id]['arm'] == 'Ax' + tag and mine[c1_id]['form_teacher'] == 'Mrs Ojo'
    assert mine[c2_id]['students'] == 0

    r = _payload(c.get(f'/academics/assignments/{c1_id}').get_data(as_text=True))
    assert sorted(e['surname'] for e in r['enrollments']) == ['Adamu', 'Musa', 'Zubair']
    assert all('first_name' in e and 'view_url' in e for e in r['enrollments'])
    assert [x['id'] for x in r['siblings']] == [c1_id, c2_id]
    assert r['assignment']['form_teacher'] == 'Mrs Ojo' and r['back_url'].endswith(f'#class-{class_id}')
