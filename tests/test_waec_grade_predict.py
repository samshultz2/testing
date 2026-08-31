"""Per-subject real-WAEC grade-band prediction from mock scores: prior / bins /
ordinal model, ordinal-aware scoring, auto method selection, and DB integration."""
from datetime import date

import pytest

from models import db, Student, WAECResult, AcademicSession
from models.mock_waec import MockWAECExam, MockWAECResult, waec_grade_from_score
import models.waec_grade_predict as W


# ---- pure-function tests (no DB) -------------------------------------------

def test_prior_sums_to_one_and_is_ordered():
    for s in (5, 30, 47, 52, 64, 72, 88, 100):
        d = W.prior_distribution(s)
        assert abs(sum(d) - 1.0) < 1e-6
    # higher score → better most-likely band and higher credit probability
    assert W.expected_grade(W.prior_distribution(82))[0] == 'A1'
    assert W.expected_grade(W.prior_distribution(30))[0] == 'F9'
    assert W.p_credit(W.prior_distribution(72)) > W.p_credit(W.prior_distribution(48))


def test_rps_is_ordinal():
    perfect = W.ranked_probability_score([1] + [0] * 8, 0)
    off1 = W.ranked_probability_score([1] + [0] * 8, 1)
    off2 = W.ranked_probability_score([1] + [0] * 8, 2)
    assert perfect == 0.0
    assert 0 < off1 < off2          # being two bands off is worse than one


def test_bins_recover_distribution_and_report_n():
    # 40 students who scored 70–74 (B2 range): 32 really got B2, 8 got B3.
    pairs = [(72.0, W._GRADE_IX['B2'])] * 32 + [(72.0, W._GRADE_IX['B3'])] * 8
    buckets = W.build_bins(pairs)
    dist, n = W.bins_predict(72, buckets)
    assert n == 40
    assert abs(sum(dist) - 1.0) < 1e-6
    assert W.GRADES[max(range(W.K), key=lambda i: dist[i])] == 'B2'
    # an empty bucket falls back toward the prior and reports n=0
    _, n0 = W.bins_predict(20, buckets)
    assert n0 == 0


def test_ordinal_model_is_monotone():
    pairs = []
    for s in range(35, 90):
        pairs += [(float(s), W._bucket_of(s))] * 3   # score → its band, noiselessly
    m = W.OrdinalModel.fit(pairs, iters=200)
    lo = m.predict(42)
    hi = m.predict(82)
    assert abs(sum(lo) - 1.0) < 1e-6 and abs(sum(hi) - 1.0) < 1e-6
    # mean grade-points should improve (drop) as the mock score rises
    assert W.expected_grade(hi)[1] < W.expected_grade(lo)[1]
    # round-trips through JSON
    m2 = W.OrdinalModel.from_json(m.to_json())
    assert m2.predict(82) == hi


def test_choose_method_thresholds():
    assert W.choose_method(5, None, 'auto') == 'prior'
    assert W.choose_method(50, None, 'auto') == 'bins'
    # plenty of data but model doesn't beat bins by the margin → stay on bins
    assert W.choose_method(300, {'rps_bins': 0.10, 'rps_model': 0.099}, 'auto') == 'bins'
    # model clearly better → promote
    assert W.choose_method(300, {'rps_bins': 0.10, 'rps_model': 0.080}, 'auto') == 'model'
    # manual override always wins
    assert W.choose_method(5, None, 'model') == 'model'
    assert W.choose_method(9999, {'rps_bins': 0.05, 'rps_model': 0.01}, 'bins') == 'bins'


# ---- DB integration --------------------------------------------------------

_SUBS = ['English Language', 'Mathematics', 'Biology', 'Chemistry', 'Physics']


def _seed_cohort(app, tag, n=12):
    """Graduate `n` students in their OWN branch (so the session-scoped test DB
    stays isolated from other suites' graduates) with a final mock (scores) and a
    real WAEC grade per subject, where the real grade roughly tracks the mock."""
    from models import Branch
    with app.app_context():
        br = (Branch.query.filter_by(code=tag).first()
              or Branch(name=f'Pred {tag}', code=tag, is_active=True))
        db.session.add(br); db.session.flush()
        ssn = (AcademicSession.query.filter_by(name=f'WP {tag}').first()
               or AcademicSession(name=f'WP {tag} 24/25', is_active=False))
        db.session.add(ssn); db.session.flush()
        ex = MockWAECExam(name=f'WP Mock {tag}', exam_number=1, session_id=ssn.id,
                          exam_date=date(2025, 3, 1), branch_id=br.id)
        db.session.add(ex); db.session.flush()
        ids = []
        for i in range(n):
            st = Student(student_id=Student.generate_student_id(), first_name=f'P{i}',
                         surname='Pred', gender='Male', is_active=True, branch_id=br.id,
                         is_graduated=True, graduation_session_id=ssn.id)
            db.session.add(st); db.session.flush()
            ids.append(st.id)
            for j, subj in enumerate(_SUBS):
                score = 50 + ((i * 7 + j * 11) % 40)         # 50–89 spread
                db.session.add(MockWAECResult(student_id=st.id, mock_exam_id=ex.id,
                                              subject=subj, score=score,
                                              grade=waec_grade_from_score(score)))
                # real grade = the mock-implied grade, nudged one band down for some
                real = waec_grade_from_score(score - (5 if i % 3 == 0 else 0))
                db.session.add(WAECResult(student_id=st.id, exam_year=2025,
                                          subject=subj, grade=real))
        db.session.commit()
        return ids, br.id


def test_training_pairs_and_predict_student(app):
    ids, bid = _seed_cohort(app, 'TP', n=12)
    with app.app_context():
        pairs = W.training_pairs(bid)
        assert set(pairs).issuperset(set(_SUBS))
        assert all(len(v) == 12 for v in (pairs[s] for s in _SUBS))

        out = W.predict_student(ids[0])
        assert out['n_subjects'] == len(_SUBS)
        for sub in out['subjects']:
            d = sub['distribution']
            assert abs(sum(d.values()) - 1.0) < 1e-3  # 4dp display rounding
            assert sub['engine'] in ('prior', 'bins', 'model')
            assert 0.0 <= sub['p_credit'] <= 1.0
        # 12 pairs/subject < MIN_PAIRS_BINS(30) → auto stays on the prior
        assert all(s['engine'] == 'prior' for s in out['subjects'])
        assert 0.0 <= out['p_both_core_credit'] <= 1.0


def test_predict_subject_bins_when_enough_data(app):
    _ids, bid = _seed_cohort(app, 'PB', n=12)
    with app.app_context():
        # Force bins regardless of count via the manual setting.
        pred = W.predict_subject(72, 'Mathematics', bid, setting='bins')
        assert pred['engine'] == 'bins'
        assert abs(sum(pred['distribution'].values()) - 1.0) < 1e-3


def test_train_models_skips_below_gate(app):
    _ids, bid = _seed_cohort(app, 'TM', n=12)
    with app.app_context():
        summary = W.train_models(bid)
        # only 12 pairs/subject → below MIN_PAIRS_MODEL, nothing trained
        assert summary and all(not r['trained'] for r in summary)
        from models import WaecGradeModel
        assert WaecGradeModel.query.filter_by(branch_id=bid).count() == 0


def test_canonical_subject_matching(app):
    """Mock 'Maths' should pair with real 'Mathematics' via canonical_subject."""
    from models import Branch
    with app.app_context():
        br = Branch(name='Canon', code='WPCANON', is_active=True)
        db.session.add(br); db.session.flush()
        ssn = AcademicSession(name='WP CANON 22/23', is_active=False)
        db.session.add(ssn); db.session.flush()
        ex = MockWAECExam(name='WPc Mock', exam_number=1, session_id=ssn.id,
                          exam_date=date(2023, 3, 1), branch_id=br.id)
        db.session.add(ex); db.session.flush()
        st = Student(student_id=Student.generate_student_id(), first_name='Q',
                     surname='Canon', gender='Female', is_active=True, branch_id=br.id,
                     is_graduated=True, graduation_session_id=ssn.id)
        db.session.add(st); db.session.flush()
        db.session.add(MockWAECResult(student_id=st.id, mock_exam_id=ex.id,
                                      subject='Maths', score=68, grade='B3'))
        db.session.add(WAECResult(student_id=st.id, exam_year=2023,
                                  subject='Mathematics', grade='B3'))
        db.session.commit()
        pairs = W.training_pairs(br.id)
        assert 'Mathematics' in pairs and pairs['Mathematics'] == [(68.0, W._GRADE_IX['B3'])]


# ---- routes ----------------------------------------------------------------

def _admin(app):
    from config import Config
    from tests.conftest import login_token, auth_csrf
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c, auth_csrf(c)


def test_waec_model_config_save_and_retrain(app):
    _seed_cohort(app, 'CFG', n=12)
    c, tok = _admin(app)
    assert c.get('/results/predictions/waec-model').status_code == 200
    # change the engine setting
    r = c.post('/results/predictions/waec-model',
               data={'action': 'save_method', 'method': 'bins', '_csrf_token': tok})
    assert r.status_code in (302, 303)
    with app.app_context():
        from models.models import SchoolSettings
        assert SchoolSettings.get('waec_prediction_method') == 'bins'
    # retrain runs without error (nothing trained — below the gate)
    r = c.post('/results/predictions/waec-model',
               data={'action': 'retrain', '_csrf_token': tok})
    assert r.status_code in (302, 303)


def test_student_predictions_page_renders_forecast(app):
    ids, _bid = _seed_cohort(app, 'PG', n=12)
    c, _ = _admin(app)
    html = c.get(f'/results/predictions/student/{ids[0]}').get_data(as_text=True)
    assert 'WAEC grade-band forecast' in html
