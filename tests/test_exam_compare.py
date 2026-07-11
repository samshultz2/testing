"""External-exams comparative analytics: headline metrics, branch ranking,
year-over-year deltas, and the hub's compare panel."""
import uuid

from config import Config
from models import db, Student, WAECResult, JAMBResult
from tests.conftest import login_token
from utils import exam_compare as ec


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def test_headline_metrics_shape_and_missing():
    m = ec.headline_metrics(
        jamb_stats={'total_students': 20, 'mean_score': 210, 'above_200': 13},
        waec_stats={'unique_students': 18, 'overall_pass_rate': 72.0,
                    'overall_distinction_rate': 12.0})
    assert m['jamb_mean'] == 210 and m['above_200_pct'] == 65.0
    assert m['waec_pass_rate'] == 72.0 and m['has_data'] is True

    empty = ec.headline_metrics(None, None)
    assert empty['has_data'] is False
    assert empty['jamb_mean'] is None and empty['above_200_pct'] is None


def test_rank_branches_orders_best_first_nulls_last():
    rows = [
        {'label': 'A', 'metrics': {'jamb_mean': 180}},
        {'label': 'B', 'metrics': {'jamb_mean': 240}},
        {'label': 'C', 'metrics': {'jamb_mean': None}},
    ]
    ranked = ec.rank_branches(rows)
    assert [r['label'] for r in ranked] == ['B', 'A', 'C']


def test_compare_years_deltas_and_direction():
    a = ec.headline_metrics(
        jamb_stats={'total_students': 10, 'mean_score': 220, 'above_200': 7},
        waec_stats={'unique_students': 10, 'overall_pass_rate': 80.0, 'overall_distinction_rate': 20.0})
    b = ec.headline_metrics(
        jamb_stats={'total_students': 10, 'mean_score': 200, 'above_200': 5},
        waec_stats={'unique_students': 10, 'overall_pass_rate': 85.0, 'overall_distinction_rate': 15.0})
    rows = {r['key']: r for r in ec.compare_years(a, b)}
    assert rows['jamb_mean']['delta'] == 20.0 and rows['jamb_mean']['improved'] is True
    # pass rate fell 5 points → not an improvement
    assert rows['waec_pass_rate']['delta'] == -5.0 and rows['waec_pass_rate']['improved'] is False


def test_compare_years_missing_side_is_na():
    a = ec.headline_metrics(jamb_stats={'total_students': 5, 'mean_score': 190, 'above_200': 2})
    b = ec.headline_metrics(None, None)
    rows = {r['key']: r for r in ec.compare_years(a, b)}
    assert rows['jamb_mean']['delta'] is None and rows['jamb_mean']['improved'] is None


# --------------------------------------------------------------------------- #
# Route wiring
# --------------------------------------------------------------------------- #
def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _seed(app, yr, mean_score):
    with app.app_context():
        s = Student(student_id='CMP' + uuid.uuid4().hex[:6].upper(), first_name='Co',
                    surname='Mpare', gender='Male')
        db.session.add(s); db.session.commit()
        db.session.add(JAMBResult(student_id=s.id, exam_year=yr, total_score=mean_score,
                                  subject1='English', subject1_score=60))
        db.session.add(WAECResult(student_id=s.id, exam_year=yr, subject='Mathematics', grade='B2'))
        db.session.commit()


def test_hub_year_comparison_panel(app):
    ya, yb = 2081, 2080
    _seed(app, ya, 260)
    _seed(app, yb, 200)
    c = _admin(app)
    html = c.get(f'/results/analytics?year={ya}&compare={yb}').get_data(as_text=True)
    assert 'Cohort comparison' in html
    assert f'{ya} vs {yb}' in html
    # the improving JAMB mean shows an up-delta
    assert 'delta up' in html


def test_hub_no_compare_panel_without_param(app):
    yr = 2082
    _seed(app, yr, 210)
    c = _admin(app)
    html = c.get(f'/results/analytics?year={yr}').get_data(as_text=True)
    assert 'Cohort comparison' not in html
    # single default branch → no branch-comparison panel
    assert 'Branch comparison' not in html
