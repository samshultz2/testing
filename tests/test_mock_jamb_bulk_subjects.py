"""Bulk Mock JAMB entry: correct answers per subject, totals worked out, and a
total-only save that keeps an existing subject breakdown."""
from models import db, Branch
from models.mock_jamb import MockJAMBResult
from tests.test_mock_jamb_notify import _admin, _csrf, _build_exam_and_student

FETCH = {'X-Requested-With': 'fetch'}


def test_bulk_per_subject_correct_answers(app):
    with app.app_context():
        bid = Branch.get_default().id
    exam_id, sid = _build_exam_and_student(app, 'BSub', bid)
    c = _admin(app)
    tok = _csrf(c)
    r = c.post(f'/mock-jamb/exam/{exam_id}/results/bulk', headers=FETCH, data={
        f'subject1_{sid}': 'English Language', f'subject1_correct_{sid}': '45',   # 75/100
        f'subject2_{sid}': 'Mathematics', f'subject2_correct_{sid}': '30',        # 75
        f'subject3_{sid}': 'Physics', f'subject3_correct_{sid}': '20',            # 50
        f'subject4_{sid}': 'Chemistry', f'subject4_correct_{sid}': '',
        '_csrf_token': tok}).get_json()
    assert r['ok'] and r['added'] == 1
    with app.app_context():
        res = MockJAMBResult.query.filter_by(student_id=sid, mock_exam_id=exam_id).one()
        assert (res.subject1_score, res.subject2_score, res.subject3_score) == (75, 75, 50)
        assert res.total_score == 200

    # A total-only save later must not wipe the subject breakdown.
    r = c.post(f'/mock-jamb/exam/{exam_id}/results/bulk', headers=FETCH,
               data={f'score_{sid}': '210', '_csrf_token': tok}).get_json()
    assert r['ok'] and r['updated'] == 1
    with app.app_context():
        res = MockJAMBResult.query.filter_by(student_id=sid, mock_exam_id=exam_id).one()
        assert res.total_score == 210 and res.subject1 == 'English Language' and res.subject1_score == 75


def test_bulk_reports_out_of_range_total(app):
    with app.app_context():
        bid = Branch.get_default().id
    exam_id, sid = _build_exam_and_student(app, 'BBad', bid)
    c = _admin(app)
    r = c.post(f'/mock-jamb/exam/{exam_id}/results/bulk', headers=FETCH,
               data={f'score_{sid}': '999', '_csrf_token': _csrf(c)}).get_json()
    assert r['ok'] and r['problems'] and 'Not saved' in r['message']


def test_bulk_payload_prefills_subjects(app):
    with app.app_context():
        bid = Branch.get_default().id
    exam_id, sid = _build_exam_and_student(app, 'BPay', bid)
    d = _admin(app).get(f'/mock-jamb/exam/{exam_id}/results/bulk',
                        headers={'Accept': 'application/json', **FETCH}).get_json()
    row = next(s for s in d['students'] if s['id'] == sid)
    assert len(row['subjects']) == 4 and row['subjects'][0]['name'] == d['compulsory_subject']
    assert d['question_counts'][d['compulsory_subject']] == 60
