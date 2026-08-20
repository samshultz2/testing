"""The promotion process page accepts an optional arm_id alongside class_id for a
more granular (single-stream) run. Smoke-test that the extra filter is accepted
and the page still renders.
"""
from config import Config
from tests.conftest import login_token


def test_process_accepts_arm_filter(app):
    from models import AcademicSession, SchoolClass
    with app.app_context():
        sess = AcademicSession.query.first()
        cls = SchoolClass.query.first()
        sess_id = sess.id if sess else 1
        cls_id = cls.id if cls else 1
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    r = c.get(f'/promotion/process?from_session_id={sess_id}&class_id={cls_id}&arm_id=9999')
    assert r.status_code == 200
