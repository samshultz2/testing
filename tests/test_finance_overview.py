"""Finance Phase 1: ledger-backed overview, filters, export, and the sync action."""
import re

from models import db, Expense, ExpenseCategory, Branch


def _admin(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['role'] = 'super_admin'
    return c


def test_summary_filters_narrow_to_a_category(app):
    from utils import finance_ledger as L
    with app.app_context():
        cat = ExpenseCategory.query.filter_by(name='OVW-UNIQCAT').first() or ExpenseCategory(name='OVW-UNIQCAT')
        db.session.add(cat); db.session.flush()
        db.session.add(Expense(description='One-off', amount=3333, category_id=cat.id,
                               method='Cash', branch_id=Branch.get_default().id))
        db.session.commit()
        s = L.summary({'category': 'OVW-UNIQCAT'})
        assert s['expense'] == 3333 and s['revenue'] == 0
        assert s['net'] == -3333
        assert any(r['key'] == 'OVW-UNIQCAT' and r['total'] == 3333 for r in s['by_expense'])


def test_overview_page_renders_for_admin(app):
    c = _admin(app)
    r = c.get('/finance/overview')
    assert r.status_code == 200 and 'fin-app' in r.get_data(as_text=True)
    d = c.get('/finance/overview', headers={'Accept': 'application/json', 'X-Requested-With': 'fetch'}).get_json()
    assert d['page'] == 'overview' and d['sync_url'] and d['export_url']
    for k in ('revenue', 'expense', 'net', 'by_source', 'by_branch', 'trend', 'recent'):
        assert k in d['ledger']


def test_overview_export_csv(app):
    c = _admin(app)
    r = c.get('/finance/overview/export')
    assert r.status_code == 200 and 'text/csv' in r.content_type
    assert r.get_data().decode('utf-8-sig').splitlines()[0].startswith('Date,Type,Source,Category,Method,Branch,Amount')


def test_ledger_sync_is_idempotent(app):
    c = _admin(app)
    page = c.get('/finance/overview').get_data(as_text=True)
    tok = re.search(r'csrf-token" content="([0-9a-f]+)"', page).group(1)
    r = c.post('/finance/ledger/sync', data={'_csrf_token': tok}, follow_redirects=False)
    assert r.status_code in (302, 303)                       # backfilled, redirect to overview
    # a second sync adds nothing (idempotent)
    from utils import finance_ledger as L
    with app.app_context():
        assert L.backfill() == 0


def test_overview_hidden_from_non_finance_user(app):
    """A logged-in user without the finance module can't reach the overview."""
    c = app.test_client()
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['role'] = 'teacher'                                # no finance module by default
    r = c.get('/finance/overview', follow_redirects=False)
    assert r.status_code in (302, 303) and '/finance' not in (r.headers.get('Location') or '')


def test_branch_totals_keep_income_and_spending_apart(app):
    """By-branch rows used to add spending onto income; now each is separate."""
    from utils import finance_ledger as L
    with app.app_context():
        s = L.summary({'branch_ids': []})
        for r in s['by_branch']:
            assert {'revenue', 'expense'} <= set(r)
            assert round(r['revenue'] - r['expense'], 2) == r['total']
        assert round(sum(r['revenue'] for r in s['by_branch']), 2) == s['revenue']
        assert round(sum(m['revenue'] for m in s['trend']), 2) <= s['revenue'] + 0.01
