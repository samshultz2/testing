"""Results Phase 2 — broadsheet + score-entry still reflect scores after the
N+1 → bulk-fetch refactor (output equivalence)."""
from config import Config
from models import db, StudentScore
from tests.conftest import login_token
from tests.test_score_integrity import _setup, _student


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _json(c, url):
    return c.get(url, headers={'Accept': 'application/json'}).get_json()


def _seed_score(app, sid, ids, value):
    with app.app_context():
        row = StudentScore.query.filter_by(student_id=sid, class_subject_id=ids['cs'],
                                           assessment_type_id=ids['at']).first()
        if row:
            row.score = value
        else:
            db.session.add(StudentScore(student_id=sid, class_subject_id=ids['cs'],
                                        assessment_type_id=ids['at'], score=value))
        db.session.commit()


def test_scores_entry_prefills_existing_score(app):
    ids = _setup(app)
    sid = _student(app, ids, 'PERF_ENTRY')
    _seed_score(app, sid, ids, 73)
    c = _admin(app)
    j = _json(c, f"/subjects/scores?term_id={ids['term']}&assignment_id={ids['asg']}"
                 f"&class_subject_id={ids['cs']}&assessment_type_id={ids['at']}")
    mine = next(s for s in j['students_data'] if s['id'] == sid)
    assert float(mine['score']) == 73


def test_broadsheet_totals_reflect_scores(app):
    ids = _setup(app)
    sid = _student(app, ids, 'PERF_BROAD')
    _seed_score(app, sid, ids, 64)
    c = _admin(app)
    j = _json(c, f"/subjects/broadsheet?term_id={ids['term']}&assignment_id={ids['asg']}")
    row = next(r for r in j['rows'] if 'PERF_BROAD' in r['student'])
    # single assessment of 64 → that subject's total is 64
    assert float(row['subjects'][str(ids['cs'])]) == 64
