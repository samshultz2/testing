"""CBT student-passwords page: the roster is built with a fixed handful of
narrow queries (no per-student lookups), however many students there are, and
every row carries the class / arm / status / search data the live filters use."""
import re
import uuid

from sqlalchemy import event

from config import Config
from models import (db, Branch, Student, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, StudentEnrollment)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _seed(app, n):
    tag = uuid.uuid4().hex[:5].upper()
    with app.app_context():
        bid = Branch.get_default().id
        term = Term.query.filter_by(is_active=True).first()
        if not term:
            s = AcademicSession(name=f'PWS{tag}', is_active=True); db.session.add(s); db.session.flush()
            term = Term(session_id=s.id, term_number=1, name='First Term', is_active=True)
            db.session.add(term); db.session.flush()
        sc = SchoolClass(name=f'PWSC{tag}', level=4, is_active=True); a1 = ClassArm(name=f'A{tag}', is_active=True)
        db.session.add_all([sc, a1]); db.session.flush()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=a1.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        for i in range(n):
            st = Student(student_id=f'PWS{tag}{i:04d}', first_name=f'F{i}', surname=f'Zpws{tag}',
                         gender='Female' if i % 2 else 'Male', is_active=True, branch_id=bid)
            if i % 3 == 0:
                st.portal_password_hash = 'x'
            db.session.add(st); db.session.flush()
            db.session.add(StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True))
        db.session.commit()
        return tag, sc.id, a1.id


def test_roster_query_count_is_constant(app):
    c = _admin(app)
    _seed(app, 5)
    counts = []
    for n in (0, 120):
        if n:
            _seed(app, n)
        seen = []
        with app.app_context():
            eng = db.engine
            listener = lambda *a, **k: seen.append(1)  # noqa: E731
            event.listen(eng, 'before_cursor_execute', listener)
            try:
                r = c.get('/cbt/passwords')
            finally:
                event.remove(eng, 'before_cursor_execute', listener)
        assert r.status_code == 200
        counts.append(len(seen))
    # 120 more students must not add queries (no N+1).
    assert counts[1] <= counts[0] + 2, counts


def test_rows_carry_live_filter_data(app):
    tag, cid, aid = _seed(app, 4)
    html = _admin(app).get('/cbt/passwords').get_data(as_text=True)
    rows = re.findall(r'<li class="pw-row" data-c="(\d+)" data-a="(\d+)" data-s="([01])" data-q="([^"]*zpws%s[^"]*)"' % tag.lower(), html)
    assert len(rows) == 4
    assert all(r[0] == str(cid) and r[1] == str(aid) for r in rows)
    assert {r[2] for r in rows} == {'0', '1'}       # i=0 has a password, others not
    assert f'data-c="{cid}"' in html and f'data-a="{aid}"' in html   # class + arm chips
    assert '.pw [hidden]{display:none!important}' in html            # hidden rows really hide
