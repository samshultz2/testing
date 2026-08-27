"""Generator streams are per school level (JSS vs SSS have their own), and the
menu's level switch drives which level's data the pages show."""
import itertools
from config import Config
from models import db, GenStream, Branch
from tests.conftest import login_token

_SEQ = itertools.count()


def _bid(app):
    with app.app_context():
        return Branch.get_default().id


def test_same_named_stream_allowed_per_level(app):
    bid = _bid(app)
    with app.app_context():
        tag = next(_SEQ)
        nm = f'Science{tag}'
        db.session.add(GenStream(name=nm, school_level='jss', branch_id=bid, is_active=True))
        db.session.add(GenStream(name=nm, school_level='sss', branch_id=bid, is_active=True))
        db.session.commit()                      # unique is (branch, name, level) -> both ok
        assert GenStream.query.filter_by(name=nm, branch_id=bid).count() == 2


def test_streams_list_scoped_to_selected_level(app):
    bid = _bid(app)
    with app.app_context():
        tag = next(_SEQ)
        db.session.add(GenStream(name=f'JOnly{tag}', school_level='jss', branch_id=bid, is_active=True))
        db.session.add(GenStream(name=f'SOnly{tag}', school_level='sss', branch_id=bid, is_active=True))
        db.session.commit()

    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})

    # Switch to JSS via the menu switcher (level_dashboard sets the session level).
    c.get('/generator/level/jss')
    body = c.get('/generator/streams').get_data(as_text=True)
    assert f'JOnly{tag}' in body and f'SOnly{tag}' not in body

    # Switch to SSS.
    c.get('/generator/level/sss')
    body = c.get('/generator/streams').get_data(as_text=True)
    assert f'SOnly{tag}' in body and f'JOnly{tag}' not in body
