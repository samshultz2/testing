"""Auto-tagging untagged bank questions (classify_confident + retag_untagged)."""


def _q(sid, text, **kw):
    from models import MockJAMBQuestion
    kw.setdefault('option_a', 'a'); kw.setdefault('option_b', 'b')
    kw.setdefault('option_c', 'c'); kw.setdefault('option_d', 'd')
    kw.setdefault('correct_option', 'A'); kw.setdefault('marks', 1)
    return MockJAMBQuestion(mock_exam_id=None, subject_id=sid, question_text=text, **kw)


def test_classify_confident_no_hash_fallback():
    """classify_confident returns nothing when no keyword matches (unlike classify,
    which falls back to a hash-picked section)."""
    from utils import myschool as ms
    assert ms.classify_confident('Mathematics', 'zzz qqq wxyz foobar') == (None, None, None)
    sec, top, _ = ms.classify_confident('Mathematics', 'Solve the quadratic equation')
    assert sec == 'algebra' and top == 'Algebra'


def test_retag_sets_topic_on_confident_match(app):
    from models import db, Subject
    from utils.mock_bank_retag import retag_untagged, untagged_count
    with app.app_context():
        s = Subject(name='Mathematics', is_active=True); db.session.add(s); db.session.flush()
        sid = s.id
        db.session.add_all([
            _q(sid, 'Solve the quadratic equation x^2 - 5x + 6 = 0'),   # matches -> tagged
            _q(sid, 'zzz qqq wxyz nonsense with no keywords'),          # no match -> left
        ])
        db.session.commit()
        assert untagged_count(s) == 2
        res = retag_untagged(s)
        assert res['scanned'] == 2
        assert res['topic_set'] == 1
        assert res['still_untagged'] == 1
        assert untagged_count(s) == 1

        from models import MockJAMBQuestion
        tagged = MockJAMBQuestion.query.filter(
            MockJAMBQuestion.subject_id == sid, MockJAMBQuestion.topic.isnot(None),
            MockJAMBQuestion.topic != '').all()
        assert len(tagged) == 1
        assert tagged[0].topic == 'Algebra'
        assert tagged[0].section == 'algebra'          # missing section filled from the match
        # shared test DB: drop this 'Mathematics' subject so it doesn't collide by
        # name with other tests' bank-draw fixtures
        MockJAMBQuestion.query.filter_by(subject_id=sid).delete()
        db.session.delete(db.session.get(Subject, sid)); db.session.commit()


def test_retag_untagged_leaves_tagged_alone(app):
    from models import db, Subject, MockJAMBQuestion
    from utils.mock_bank_retag import retag_untagged
    with app.app_context():
        s = Subject(name='Mathematics', is_active=True); db.session.add(s); db.session.flush()
        sid = s.id
        db.session.add(_q(sid, 'Solve the quadratic equation', topic='Hand-picked', section='geometry'))
        db.session.commit()
        res = retag_untagged(s)                          # default mode='untagged'
        assert res['scanned'] == 0                      # already tagged -> not scanned
        q = MockJAMBQuestion.query.filter_by(subject_id=sid).first()
        assert q.topic == 'Hand-picked' and q.section == 'geometry'
        MockJAMBQuestion.query.filter_by(subject_id=sid).delete()
        db.session.delete(db.session.get(Subject, sid)); db.session.commit()


def test_retag_all_upgrades_existing_tag(app):
    """mode='all' re-classifies already-tagged questions so improved keywords
    replace a stale/generic tag (but only on a confident match)."""
    from models import db, Subject, MockJAMBQuestion
    from utils.mock_bank_retag import retag_untagged
    with app.app_context():
        s = Subject(name='Mathematics', is_active=True); db.session.add(s); db.session.flush()
        sid = s.id
        db.session.add(_q(sid, 'Solve the quadratic equation x^2 - 5x + 6 = 0',
                          topic='Wrong', section='statistics'))
        db.session.commit()
        res = retag_untagged(s, mode='all')
        assert res['scanned'] == 1 and res['topic_set'] == 1
        q = MockJAMBQuestion.query.filter_by(subject_id=sid).first()
        assert q.topic == 'Algebra'                     # upgraded from 'Wrong'
        MockJAMBQuestion.query.filter_by(subject_id=sid).delete()
        db.session.delete(db.session.get(Subject, sid)); db.session.commit()


def test_retag_ensure_section_makes_unmatched_drawable(app):
    """ensure_section gives an unmatched question a valid, non-passage blueprint
    section so it's usable in exams even without a topic."""
    from models import db, Subject, MockJAMBQuestion
    from utils.mock_bank_retag import retag_untagged
    from utils.jamb_blueprint import sections_for
    with app.app_context():
        s = Subject(name='Mathematics', is_active=True); db.session.add(s); db.session.flush()
        sid = s.id
        db.session.add(_q(sid, 'zzz qqq no keywords here', section=None))
        db.session.commit()
        res = retag_untagged(s, mode='all', ensure_section=True)
        assert res['topic_set'] == 0 and res['section_ensured'] == 1
        q = MockJAMBQuestion.query.filter_by(subject_id=sid).first()
        valid = {x['section'] for x in sections_for('Mathematics') if not x['passage']}
        assert q.section in valid                        # now drawable
        assert q.topic in (None, '')                     # but no invented topic
        MockJAMBQuestion.query.filter_by(subject_id=sid).delete()
        db.session.delete(db.session.get(Subject, sid)); db.session.commit()


def test_retag_apostrophe_boost_matches(app):
    """The curly/straight apostrophe fold means an Ohm's-law question tags (its
    boost key uses a straight apostrophe, the syllabus a curly one)."""
    from utils import myschool as ms
    sec, top, sub = ms.classify_confident('Physics', 'Find the resistance using Ohm law: V = IR')
    assert top is not None
