"""Self-scope Library loans — a staff borrower sees only their OWN borrowed
books on /account, read-only, with no access to the Library module itself."""
from datetime import date, timedelta
from flask import session
from models import db, User, StaffMember, Branch, Book, BookLoan


def _staff_user_with_loan(app, username, perms, title):
    with app.app_context():
        bid = Branch.get_default().id
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, full_name=username.title(), role='staff',
                     scope='branch', branch_id=bid)
            u.set_password('CorrectHorse9')
            db.session.add(u); db.session.flush()
        u.is_active = True
        u.set_permissions(perms)
        s = StaffMember.query.filter_by(user_id=u.id).first()
        if not s:
            s = StaffMember(first_name='Lib', surname=username.title(), is_active=True,
                            status='Active', staff_type='Teaching', branch_id=bid, user_id=u.id)
            db.session.add(s); db.session.flush()
        bk = Book.query.filter_by(title=title).first()
        if not bk:
            bk = Book(title=title)
            db.session.add(bk); db.session.flush()
        if not BookLoan.query.filter_by(book_id=bk.id, staff_id=s.id, status='Borrowed').first():
            db.session.add(BookLoan(book_id=bk.id, borrower_type='staff', staff_id=s.id,
                                    status='Borrowed', borrowed_date=date.today(),
                                    due_date=date.today() - timedelta(days=3)))  # overdue
        db.session.commit()
        return u.id, s.id


def test_self_loans_registered(app):
    from utils.access_control import (CAPABILITY_SUBSECTIONS, SELF_SCOPE_SUBSECTIONS,
                                      MODULE_SUBSECTIONS)
    assert 'library.self_loans' in CAPABILITY_SUBSECTIONS
    assert 'library.self_loans' in SELF_SCOPE_SUBSECTIONS
    assert 'self_loans' in MODULE_SUBSECTIONS['library']


def test_self_loans_shows_own_only_not_module(app):
    uid, sid = _staff_user_with_loan(app, 'lib_self', {'library.self_loans': 'view'}, 'ZZ My Book')
    # A different staff member's loan must never leak in.
    other_uid, _ = _staff_user_with_loan(app, 'lib_other', {'library.self_loans': 'view'}, 'ZZ Other Book')
    with app.test_request_context('/'):
        session.update(logged_in=True, user_id=uid, role='staff')
        from utils.access_control import can_access_module, self_scope_level
        from utils.self_service import library_self_loans
        assert can_access_module('library') is False        # capability != module access
        assert self_scope_level('library.self_loans') == 'view'
        data = library_self_loans(db.session.get(User, uid))
        assert data is not None
        titles = {r['title'] for r in data['loans']}
        assert 'ZZ My Book' in titles and 'ZZ Other Book' not in titles
        assert data['overdue'] >= 1                          # the seeded loan is overdue


def test_self_loans_none_without_capability(app):
    uid, sid = _staff_user_with_loan(app, 'lib_nocap', {'students': 'view'}, 'ZZ NoCap Book')
    with app.test_request_context('/'):
        session.update(logged_in=True, user_id=uid, role='staff')
        from utils.self_service import library_self_loans
        assert library_self_loans(db.session.get(User, uid)) is None
