"""MathJax (1.17MB) is the heaviest single asset on the CBT and Mock JAMB
student sitting pages. It must load only when a question/option actually
contains math markup, and each page must keep respecting its own delimiter
config (CBT treats $ / $$ as math; Mock JAMB deliberately does not, to avoid
mistaking a currency amount for LaTeX)."""
from datetime import date
from models import (db, CBTExam, CBTQuestion, CBTAttempt, Student, Subject, Branch,
                    AcademicSession, MockJAMBExam, MockJAMBQuestion,
                    StudentEnrollment, SchoolClass, ClassArm, ClassArmAssignment, Term)
import routes.cbt as cbt

_MATHJAX_MARKER = b'mathjax-setup'
_SEQ = [0]


def _get_or_create(model, defaults=None, **kw):
    obj = model.query.filter_by(**kw).first()
    if obj:
        return obj
    obj = model(**kw, **(defaults or {}))
    db.session.add(obj); db.session.flush()
    return obj


def _cbt_exam(app, sid, q1_text, q1_opts):
    """A published-class exam + a student properly placed (enrollment +
    class/arm assignment) so take() 's _student_can_access() check passes."""
    with app.app_context():
        _SEQ[0] += 1
        bid = Branch.get_default().id
        # get_active_term() picks the (session, term) both flagged active —
        # deactivate any earlier test's so this one is unambiguously current.
        AcademicSession.query.update({AcademicSession.is_active: False})
        Term.query.update({Term.is_active: False})
        sess = _get_or_create(AcademicSession, name=f'MJX-{_SEQ[0]}-S', defaults={'is_active': True})
        sess.is_active = True
        term = _get_or_create(Term, session_id=sess.id, term_number=1,
                              defaults={'name': f'MJX-{_SEQ[0]}-T', 'is_active': True})
        term.is_active = True
        cls = _get_or_create(SchoolClass, name=f'MJX-{_SEQ[0]}', defaults={'level': 12})
        arm = _get_or_create(ClassArm, name=f'MJX{_SEQ[0]}A')
        caa = _get_or_create(ClassArmAssignment, class_id=cls.id, arm_id=arm.id,
                             term_id=term.id, defaults={'branch_id': bid})
        s = Student(student_id=sid, first_name='M', surname='Jax',
                    gender='Male', is_active=True, branch_id=bid)
        db.session.add(s); db.session.flush()
        db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id,
                                          is_active=True))
        e = CBTExam(title='MathJax Exam', class_id=cls.id); db.session.add(e); db.session.flush()
        q = CBTQuestion(exam_id=e.id, question_text=q1_text, correct_option='A', marks=1,
                         option_a=q1_opts[0], option_b=q1_opts[1],
                         option_c=q1_opts[2], option_d=q1_opts[3])
        db.session.add(q); db.session.flush()
        db.session.add(CBTAttempt(exam_id=e.id, student_id=s.id, status='In progress'))
        db.session.commit()
        return e.id, s.id


def _cbt_take(app, eid, sid):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess[cbt.PORTAL_KEY] = sid
    return c.get(f'/exam/{eid}/take')


def test_cbt_skips_mathjax_when_no_math(app):
    eid, sid = _cbt_exam(app, 'MJNONE', 'What is the capital of Nigeria?',
                         ('Lagos', 'Abuja', 'Kano', 'Ibadan'))
    r = _cbt_take(app, eid, sid)
    assert r.status_code == 200
    assert _MATHJAX_MARKER not in r.data


def test_cbt_loads_mathjax_for_latex_escapes(app):
    eid, sid = _cbt_exam(app, 'MJLATEX', r'Simplify \(x^2 + 2x\)',
                         ('a', 'b', 'c', 'd'))
    r = _cbt_take(app, eid, sid)
    assert r.status_code == 200
    assert _MATHJAX_MARKER in r.data


def test_cbt_loads_mathjax_for_dollar_delims():
    """CBT's own config treats $ ... $ as math — the detector must match."""
    from utils.mathjax_content import has_math_markup
    assert has_math_markup('The value is $x$ here') is True


def _mock_jamb_exam(app, sid, q1_text):
    with app.app_context():
        _SEQ[0] += 1
        bid = Branch.get_default().id
        subj = Subject.query.filter_by(name='English Language').first() or Subject(name='English Language', is_active=True)
        db.session.add(subj); db.session.flush()
        sess_ = AcademicSession(name=f'MJ-{_SEQ[0]}'); db.session.add(sess_); db.session.flush()
        ex = MockJAMBExam(name=f'Mock {_SEQ[0]}', exam_number=1, session_id=sess_.id,
                          exam_date=date(2025, 3, 1), branch_id=bid,
                          is_published=True, duration_minutes=90)
        db.session.add(ex); db.session.flush()
        db.session.add(MockJAMBQuestion(
            mock_exam_id=ex.id, subject_id=subj.id, question_text=q1_text,
            option_a='a', option_b='b', option_c='c', option_d='d',
            correct_option='A', marks=1, order=1))
        st = Student(student_id=sid, first_name='M', surname='Jax',
                     gender='Male', is_active=True, branch_id=bid,
                     jamb_subjects='English Language')
        st.set_portal_password('pass1234')
        db.session.add(st); db.session.commit()
        return ex.id, st.id


def _mock_jamb_login(app, student_id):
    c = app.test_client()
    with app.app_context():
        sid_code = db.session.get(Student, student_id).student_id
    import re
    html = c.get('/exam/login').get_data(as_text=True)
    m = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', html) or re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    tok = m.group(1) if m else None
    c.post('/exam/login', data={'student_id': sid_code, 'password': 'pass1234', '_csrf_token': tok},
           follow_redirects=True)
    return c


def test_mock_jamb_skips_mathjax_when_no_math(app):
    eid, sid = _mock_jamb_exam(app, 'MJPNONE', 'Choose the correct synonym for "happy".')
    c = _mock_jamb_login(app, sid)
    r = c.get(f'/exam/mock-jamb/{eid}')
    assert r.status_code == 200
    assert _MATHJAX_MARKER not in r.data


def test_mock_jamb_loads_mathjax_for_latex_escapes(app):
    eid, sid = _mock_jamb_exam(app, 'MJPLATEX', r'Evaluate \[ \int_0^1 x\,dx \]')
    c = _mock_jamb_login(app, sid)
    r = c.get(f'/exam/mock-jamb/{eid}')
    assert r.status_code == 200
    assert _MATHJAX_MARKER in r.data


def test_mock_jamb_ignores_dollar_amounts():
    """Mock JAMB's config deliberately drops $ / $$ as delimiters (see
    static/js/mathjax-setup.js) so a currency amount isn't mistaken for math."""
    from utils.mathjax_content import has_math_markup
    assert has_math_markup('He was paid $50 for the job', dollar_delims=False) is False
    # but a real LaTeX escape still counts, dollar delimiters or not
    assert has_math_markup(r'Simplify \(x^2\)', dollar_delims=False) is True
