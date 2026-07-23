"""Bank bulk-delete: clear a subject's questions by scope (all / untagged / source / year)."""
from config import Config
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    import re
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', c.get('/students').get_data(as_text=True))
    return m.group(1)


def _seed(app):
    from models import db, Subject, MockJAMBQuestion
    with app.app_context():
        s = Subject(name='BulkDelCommerce', is_active=True); db.session.add(s); db.session.flush()
        # 3 untagged ALOC questions + 2 tagged myschool ones
        for i in range(3):
            db.session.add(MockJAMBQuestion(
                mock_exam_id=None, subject_id=s.id, question_text=f'aloc q{i}',
                option_a='a', option_b='b', option_c='c', option_d='d',
                correct_option='A', marks=1, source='aloc', topic=None, order=i))
        for i in range(2):
            db.session.add(MockJAMBQuestion(
                mock_exam_id=None, subject_id=s.id, question_text=f'ms q{i}',
                option_a='a', option_b='b', option_c='c', option_d='d',
                correct_option='B', marks=1, source='myschool', topic='Trade',
                exam_year='2019', order=10 + i))
        db.session.commit()
        return s.id


def _count(app, sid, **filt):
    from models import db, MockJAMBQuestion
    with app.app_context():
        q = MockJAMBQuestion.query.filter_by(subject_id=sid, mock_exam_id=None)
        for k, v in filt.items():
            q = q.filter(getattr(MockJAMBQuestion, k) == v)
        return q.count()


def test_delete_by_source(app):
    sid = _seed(app)
    c = _admin(app)
    c.post('/mock-jamb/bank/delete-bulk',
           data={'_csrf_token': _csrf(c), 'subject_id': sid, 'scope': 'source', 'source': 'aloc'},
           follow_redirects=True)
    assert _count(app, sid, source='aloc') == 0
    assert _count(app, sid, source='myschool') == 2      # other source untouched


def test_delete_untagged_only(app):
    sid = _seed(app)
    c = _admin(app)
    c.post('/mock-jamb/bank/delete-bulk',
           data={'_csrf_token': _csrf(c), 'subject_id': sid, 'scope': 'untagged'},
           follow_redirects=True)
    assert _count(app, sid) == 2                          # only the tagged ones remain


def test_delete_all_in_subject(app):
    sid = _seed(app)
    c = _admin(app)
    c.post('/mock-jamb/bank/delete-bulk',
           data={'_csrf_token': _csrf(c), 'subject_id': sid, 'scope': 'all'},
           follow_redirects=True)
    assert _count(app, sid) == 0
