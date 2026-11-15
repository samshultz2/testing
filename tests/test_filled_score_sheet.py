"""Score entry → "Print scores": the same score sheet as the blank one, filled
with every saved score, the Exam Total (P.E/M.E + CBT + PBT/Theory) and General Total."""
from config import Config
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm, ClassArmAssignment,
                    Student, StudentEnrollment, Subject, ClassSubject, AssessmentType, StudentScore)
from tests.conftest import login_token

_SEQ = [0]


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _seed(app):
    with app.app_context():
        _SEQ[0] += 1
        tag = f'FSS{_SEQ[0]}'
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'{tag}-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='First Term'); db.session.add(term); db.session.flush()
        sc = SchoolClass(name=f'{tag}C', level=1); arm = ClassArm(name=f'{tag}A', is_active=True)
        db.session.add_all([sc, arm]); db.session.flush()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        subj = Subject(name=f'{tag} Geography', is_active=True); db.session.add(subj); db.session.flush()
        cs = ClassSubject(subject_id=subj.id, class_id=sc.id, arm_id=arm.id, term_id=term.id, is_active=True)
        db.session.add(cs); db.session.flush()
        a = Student(student_id=f'{tag}-1', first_name='Ada', surname='Filledsheet', gender='Female', is_active=True, branch_id=bid)
        b = Student(student_id=f'{tag}-2', first_name='Bayo', surname='Noscores', gender='Male', is_active=True, branch_id=bid)
        db.session.add_all([a, b]); db.session.flush()
        for s in (a, b):
            db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id, is_active=True))
        from utils.broadsheet_export import score_columns
        cols = score_columns(subject=subj, term_id=term.id)
        # give Ada every column at (max - 1) so totals are predictable
        for c in cols:
            db.session.add(StudentScore(student_id=a.id, class_subject_id=cs.id, assessment_type_id=c['ids'][0],
                                        score=c['max'] - 1))
        db.session.commit()
        exam = sum(c['max'] - 1 for c in cols if c['kind'] in ('peme', 'cbt', 'theory'))
        total = sum(c['max'] - 1 for c in cols)
        return dict(term=term.id, asg=caa.id, cs=cs.id, exam=exam, total=total, n=len(cols))


def _text(pdf):
    import fitz
    d = fitz.open(stream=pdf, filetype='pdf')
    try:
        return '\n'.join(p.get_text() for p in d)
    finally:
        d.close()


def test_print_scores_fills_the_sheet(app):
    ids = _seed(app)
    c = _admin(app)
    # the score-entry page offers the button once a subject is picked
    d = c.get(f"/subjects/scores?term_id={ids['term']}&assignment_id={ids['asg']}&class_subject_id={ids['cs']}",
              headers={'X-Requested-With': 'fetch'}).get_json()
    d = d.get('data', d)
    url = d['urls']['filled_sheet']
    assert 'filled=1' in url
    r = c.get(url)
    assert r.status_code == 200 and r.mimetype == 'application/pdf'
    assert 'scores_' in r.headers.get('Content-Disposition', '')
    text = _text(r.data)
    assert 'Filledsheet' in text and 'Noscores' in text
    assert str(ids['total']) in text and str(ids['exam']) in text      # totals filled in
    assert '1 of 2 students have scores' in text
    assert 'Subject teacher' in text


def test_blank_sheet_is_still_blank(app):
    ids = _seed(app)
    c = _admin(app)
    r = c.get(f"/subjects/broadsheet/blank-sheet?term_id={ids['term']}&assignment_id={ids['asg']}&class_subject_id={ids['cs']}")
    text = _text(r.data)
    assert str(ids['total']) not in text and 'students have scores' not in text


def _rows(pdf):
    """Each student's row text from the sheet, keyed by surname."""
    import fitz
    d = fitz.open(stream=pdf, filetype='pdf')
    try:
        words = d[0].get_text('words')
    finally:
        d.close()
    out = {}
    for name in ('Filledsheet', 'Noscores'):
        w = next(x for x in words if x[4] == name)
        y = (w[1] + w[3]) / 2
        out[name] = [x[4] for x in sorted(words, key=lambda x: x[0]) if x[1] < y < x[3]]
    return out


def test_choose_which_columns_to_fill(app):
    ids = _seed(app)
    c = _admin(app)
    d = c.get(f"/subjects/scores?term_id={ids['term']}&assignment_id={ids['asg']}&class_subject_id={ids['cs']}",
              headers={'X-Requested-With': 'fetch'}).get_json()
    d = d.get('data', d)
    keys = [x['key'] for x in d['sheet_cols']]
    assert 'CBT' in keys and 'EXAM_TOTAL' in keys and 'GENERAL_TOTAL' in keys
    base = d['urls']['filled_sheet']
    cbt_max = next(x['max'] for x in d['sheet_cols'] if x['key'] == 'CBT')

    # CBT only: just the CBT score on Ada's row; every other column (and both totals) empty
    row = _rows(c.get(base + '&fill=CBT').data)['Filledsheet']
    nums = [w for w in row if w.replace('.', '').isdigit()]
    assert nums[1:] == [str(cbt_max - 1)], row          # S/N then the CBT score only

    # no totals: every score, but the two total columns empty
    row = _rows(c.get(base + '&fill=' + ','.join(k for k in keys if 'TOTAL' not in k)).data)['Filledsheet']
    nums = [w for w in row if w.replace('.', '').isdigit()][1:]
    assert len(nums) == ids['n'] and str(ids['total']) not in nums

    # nothing ticked → a blank sheet for this subject (headings still show maxima)
    row = _rows(c.get(base + '&fill=').data)['Filledsheet']
    assert [w for w in row if w.replace('.', '').isdigit()][1:] == []


def test_exam_total_includes_peme(app):
    """Exam Total = P.E/M.E + CBT + PBT/Theory (its heading maximum too)."""
    ids = _seed(app)
    c = _admin(app)
    d = c.get(f"/subjects/scores?term_id={ids['term']}&assignment_id={ids['asg']}&class_subject_id={ids['cs']}",
              headers={'X-Requested-With': 'fetch'}).get_json()
    d = d.get('data', d)
    cols = {x['key']: x for x in d['sheet_cols']}
    peme = next((x for x in d['sheet_cols'] if x['kind'] == 'peme'), None)
    assert peme is not None
    exam_parts = [x['max'] for x in d['sheet_cols'] if x['kind'] in ('peme', 'cbt', 'theory')]
    assert cols['EXAM_TOTAL']['max'] == sum(exam_parts)
    row = _rows(c.get(d['urls']['filled_sheet'] + '&fill=EXAM_TOTAL').data)['Filledsheet']
    nums = [w for w in row if w.replace('.', '').isdigit()][1:]
    assert nums == [str(ids['exam'])]                       # includes P.E/M.E
