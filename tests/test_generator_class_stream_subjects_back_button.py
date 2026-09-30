"""Timetable generator: /generator/classes/<id>/stream-subjects should have
a back button to the class's subjects config page, like the other
generator sub-pages reached from there."""
from config import Config
from models import db, Branch, GenClassConfig, GenStream, GenClassArmStream
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _build_streamed_class(app, tag):
    with app.app_context():
        bid = Branch.get_default().id
        cc = GenClassConfig(branch_id=bid, class_name=f'ZzSSS3{tag}', school_level='sss',
                            num_arms=1, arm_names=f'ZzArm{tag}', has_streams=True)
        db.session.add(cc); db.session.flush()

        stream = GenStream(branch_id=bid, name=f'ZzScience{tag}', school_level='sss')
        db.session.add(stream); db.session.flush()

        db.session.add(GenClassArmStream(class_config_id=cc.id, arm_name=f'ZzArm{tag}', stream_id=stream.id))
        db.session.commit()
        return cc.id


def test_class_stream_subjects_has_back_button(app):
    cc_id = _build_streamed_class(app, 'BB')
    c = _admin(app)
    body = c.get(f'/generator/classes/{cc_id}/stream-subjects').get_data(as_text=True)
    assert 'Back to' in body
    assert f'/generator/class-subjects/{cc_id}' in body
