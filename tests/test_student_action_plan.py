"""Student action plan — the narrative + prioritised-recommendation synthesis
layer, and its view route (roadmap #8)."""
from models import db, Branch, Student, WAECResult
from config import Config
from utils.student_action_plan import build_action_plan

_YR = 2264
_SEQ = [0]


def _student(app, grades):
    with app.app_context():
        bid = Branch.get_default().id
        _SEQ[0] += 1
        st = Student(student_id=f'SAP-{_SEQ[0]}', first_name='Sam', surname=f'Plan{_SEQ[0]}',
                     gender='Male', is_active=True, branch_id=bid)
        db.session.add(st); db.session.flush()
        for sub, g in (grades or {}).items():
            db.session.add(WAECResult(student_id=st.id, exam_year=_YR, subject=sub, grade=g))
        db.session.commit()
        return st.id


def _admin(app):
    from tests.conftest import login_token
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_weak_student_gets_high_priority_actions(app):
    # 3 credits, no Maths credit → below the 5-credit + core bar
    sid = _student(app, {'English Language': 'C6', 'Biology': 'C5', 'Physics': 'C4',
                         'Mathematics': 'F9', 'Chemistry': 'F9'})
    with app.app_context():
        plan = build_action_plan(db.session.get(Student, sid))
        assert plan['status'] in ('NOT_READY', 'AT_RISK', 'CONDITIONAL')
        assert plan['narrative']
        assert any(a['priority'] == 'HIGH' for a in plan['actions'])
        # a core-subject / credit blocker should surface
        joined = ' '.join(a['recommendation'].lower() for a in plan['actions'])
        assert 'credit' in joined or 'mathematics' in joined


def test_no_data_student_is_graceful(app):
    sid = _student(app, {})
    with app.app_context():
        plan = build_action_plan(db.session.get(Student, sid))
        assert plan['status'] == 'NO_DATA'
        assert plan['actions']              # should recommend recording results
        assert all('area' in a and 'priority' in a for a in plan['actions'])


def test_action_plan_route_html_and_json(app):
    sid = _student(app, {'English Language': 'C6', 'Mathematics': 'F9', 'Biology': 'C5'})
    c = _admin(app)
    r = c.get(f'/results/student/{sid}/action-plan')
    assert r.status_code == 200 and 'Action Plan' in r.get_data(as_text=True)
    j = c.get(f'/results/student/{sid}/action-plan?format=json').get_json()
    assert set(j) >= {'status', 'narrative', 'actions', 'risk_level'}
    assert isinstance(j['actions'], list)
