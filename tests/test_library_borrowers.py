"""Library Phase 3 — borrower directory + history, and automated reminders."""
import re
from datetime import date, timedelta

from config import Config
from models import db, Book, BookLoan, Student, StaffMember, ParentContact
from tests.conftest import login_token


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def _seed(app, tag, *, overdue=True, parent=True):
    with app.app_context():
        b = Book(title=f'BB {tag}', copies_total=3, copies_available=1)
        # Surname sorts last so these students don't displace the first recipient
        # in other tests' shared-DB 'all' audience (order-dependent assertions).
        st = Student(student_id=f'BS{tag}', first_name='Ada', surname=f'Zzlib{tag}',
                     gender='Female', is_active=True)
        sf = StaffMember(staff_id=f'BF{tag}', first_name='Mr', surname=f'C{tag}',
                         staff_type='Teaching', is_active=True)
        db.session.add_all([b, st, sf])
        db.session.flush()
        if parent:
            db.session.add(ParentContact(student_id=st.id, phone_number=f'0805000{tag[-4:]}',
                                         is_primary=True))
        due = date.today() - timedelta(days=4) if overdue else date.today() + timedelta(days=7)
        db.session.add(BookLoan(book_id=b.id, student_id=st.id, borrower_type='student',
                                borrowed_date=date.today() - timedelta(days=10),
                                due_date=due, status='Borrowed'))
        db.session.add(BookLoan(book_id=b.id, staff_id=sf.id, borrower_type='staff',
                                borrowed_date=date.today(), due_date=date.today() + timedelta(days=10),
                                status='Borrowed'))
        db.session.commit()
        return b.id, st.id, sf.id


# --- directory + history ----------------------------------------------------
def test_borrowers_directory_lists_and_aggregates(app):
    bid, sid, sfid = _seed(app, 'DIR1')
    client = _admin(app)
    html = client.get('/library/borrowers').get_data(as_text=True)
    assert '"page": "borrowers"' in html and '"borrowers"' in html
    assert 'BSDIR1' in html and 'BFDIR1' in html   # both student and staff appear


def test_borrower_history_student(app):
    bid, sid, sfid = _seed(app, 'HIS1')
    client = _admin(app)
    html = client.get(f'/library/borrower/student/{sid}').get_data(as_text=True)
    assert '"page": "borrower"' in html
    for key in ('"stats"', '"current"', '"past"', '"overdue"'):
        assert key in html


def test_borrower_history_staff(app):
    bid, sid, sfid = _seed(app, 'HIS2')
    client = _admin(app)
    html = client.get(f'/library/borrower/staff/{sfid}').get_data(as_text=True)
    assert '"page": "borrower"' in html and '"type": "staff"' in html


# --- automated reminders ----------------------------------------------------
def test_library_reminders_registered_in_automation_center(app):
    from utils import automations
    with app.app_context():
        assert 'library_overdue' in automations.KEYS
        assert 'library_due_soon' in automations.KEYS


def test_reminders_respect_automation_toggle(app):
    _seed(app, 'AUTO1', overdue=True, parent=True)
    from utils import automations, library_notify
    from models import Notification
    with app.app_context():
        # disabled -> no work
        automations.set_enabled('library_overdue', False)
        automations.set_enabled('library_due_soon', False)
    out = library_notify.run_library_reminders(app)   # not forced
    assert out == {}
    # forced dry-run reports counts without side effects
    dry = library_notify.run_library_reminders(app, force=True, dry_run=True)
    assert 'overdue' in dry and dry['overdue'] >= 1
    # restore to enabled state used elsewhere (registry default is off, keep off)


def test_reminders_notify_and_draft_when_enabled(app):
    _seed(app, 'AUTO2', overdue=True, parent=True)
    from utils import automations, library_notify
    from models import Notification, Message
    with app.app_context():
        before = Notification.query.filter(Notification.title == 'Library: overdue books').count()
    library_notify.run_library_reminders(app, force=True)
    with app.app_context():
        assert Notification.query.filter(Notification.title == 'Library: overdue books').count() > 0
        # a parent draft campaign was queued (guarded to once/day)
        assert Message.query.filter_by(title='Library overdue reminder').count() >= 1
