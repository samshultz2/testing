"""Finance Phase 2: double-entry statements derived from the ledger."""
from models import db, Expense, ExpenseCategory, Branch


def test_statements_balance_and_match_ledger(app):
    from utils import finance_ledger as L, finance_accounting as A
    with app.app_context():
        f = {}                                    # whole ledger
        tb = A.trial_balance(f)
        assert tb['balanced']
        assert abs(tb['total_debit'] - tb['total_credit']) < 0.5

        pl = A.income_statement(f)
        s = L.summary(f)
        assert abs(pl['total_income'] - s['revenue']) < 0.5
        assert abs(pl['total_expense'] - s['expense']) < 0.5
        assert abs(pl['net'] - s['net']) < 0.5

        bs = A.balance_sheet(f)
        assert bs['balanced']
        assert abs(bs['total_assets'] - bs['total_equity']) < 0.5


def test_journal_mapping_for_isolated_expense(app):
    """A cash expense debits its Expense account and credits Cash, equally."""
    from utils import finance_accounting as A
    with app.app_context():
        cat = ExpenseCategory.query.filter_by(name='ACCT-UNIQ').first() or ExpenseCategory(name='ACCT-UNIQ')
        db.session.add(cat); db.session.flush()
        db.session.add(Expense(description='Isolated', amount=900, category_id=cat.id,
                               method='Cash', branch_id=Branch.get_default().id))
        db.session.commit()

        f = {'category': 'ACCT-UNIQ'}
        tb = A.trial_balance(f)
        exp = [a for a in tb['accounts'] if a['type'] == 'Expense']
        cash = [a for a in tb['accounts'] if a['name'] == 'Cash']
        assert exp and exp[0]['debit'] == 900
        assert cash and cash[0]['credit'] == 900
        assert tb['total_debit'] == tb['total_credit'] == 900

        pl = A.income_statement(f)
        assert pl['total_expense'] == 900 and pl['total_income'] == 0 and pl['net'] == -900


def test_income_statement_breaks_out_cogs(app):
    """A COGS ledger entry becomes its own line and a Gross Profit subtotal,
    while still counting in total_expense / net (accounting stays connected)."""
    from utils import finance_ledger as L, finance_accounting as A
    with app.app_context():
        L.post(L.REVENUE, 1000, source_module='sales', category='Bookshop',
               method='Cash', branch_id=Branch.get_default().id,
               origin_type='test_sale', origin_id=99001)
        L.post(L.EXPENSE, 300, source_module='cogs', category=L.COGS_CATEGORY,
               method='Cash', branch_id=Branch.get_default().id,
               origin_type='test_cogs', origin_id=99001)
        db.session.commit()
        f = {'origin_type': None}
        pl = A.income_statement({'source_module': None})
        # gross profit excludes COGS from the top line; net still includes it
        assert pl['cogs'] >= 300
        assert abs(pl['gross_profit'] - (pl['total_income'] - pl['cogs'])) < 0.5
        assert abs(pl['net'] - (pl['total_income'] - pl['total_expense'])) < 0.5
        assert L.COGS_CATEGORY not in {r['name'] for r in pl['operating_expense']}


def test_accounting_page_renders_for_admin(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['role'] = 'super_admin'
    r = c.get('/finance/accounting')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    for m in ('Income Statement', 'Balance Sheet', 'Trial Balance', 'Cash Flow', 'Chart of Accounts'):
        assert m in body


def test_accounting_export_xlsx(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['role'] = 'super_admin'
    r = c.get('/finance/accounting/export')
    assert r.status_code == 200
    assert 'spreadsheetml' in r.content_type or r.content_type.endswith('.sheet') \
        or 'officedocument' in r.content_type
