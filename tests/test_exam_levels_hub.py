"""External exams hub (/exam-levels/): every exam by level, latest year vs the
one before, "needs attention" alerts, and partial years not raising alarms."""
import uuid

from config import Config
from models import db, Student, JAMBResult
from tests.conftest import login_token
from utils import exam_levels_overview as XO


def _client(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_hub_renders_every_level_and_exam(app):
    c = _client(app)
    r = c.get('/exam-levels/')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for s in ('External exams', 'SSS3', 'JSS3', 'WAEC (WASSCE)', 'NECO (SSCE)', 'JAMB (UTME)',
              'Mock WAEC', 'Mock JAMB', 'State BECE', 'State vs Federal'):
        assert s in html, s


def test_jamb_tile_change_and_partial_year(app):
    with app.test_request_context():
        ids = []
        for i in range(10):
            s = Student(student_id='XL' + uuid.uuid4().hex[:6].upper(), first_name='X%d' % i, surname='Hub',
                        gender='Male', is_active=True)
            db.session.add(s); db.session.flush(); ids.append(s.id)
        for sid in ids:
            db.session.add(JAMBResult(student_id=sid, exam_year=2091, total_score=200))
        db.session.add(JAMBResult(student_id=ids[0], exam_year=2092, total_score=150))
        db.session.commit()
        hub = XO.build(lambda lv: __import__('routes.school_exams', fromlist=['_LiveMeta'])._LiveMeta(lv))
        jamb = next(e for e in hub['levels'][0]['exams'] if e['name'] == 'JAMB (UTME)')
        assert jamb['period'] == '2092'
        # 1 candidate vs 10 last year: flagged in progress, no "down" alarm
        assert jamb.get('partial') and jamb['delta'] is None
        assert not any('JAMB (UTME) 2092: average score' in a['text'] for a in hub['attention'])
        assert any('scored below 160 in JAMB (UTME) 2092' in a['text'] for a in hub['attention'])
        JAMBResult.query.filter(JAMBResult.exam_year.in_([2091, 2092])).delete()
        db.session.commit()
