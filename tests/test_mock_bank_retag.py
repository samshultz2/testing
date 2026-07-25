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


def test_retag_does_not_overwrite_existing_topic(app):
    from models import db, Subject, MockJAMBQuestion
    from utils.mock_bank_retag import retag_untagged
    with app.app_context():
        s = Subject(name='Mathematics', is_active=True); db.session.add(s); db.session.flush()
        sid = s.id
        db.session.add(_q(sid, 'Solve the quadratic equation', topic='Hand-picked', section='geometry'))
        db.session.commit()
        res = retag_untagged(s)
        assert res['scanned'] == 0                      # already tagged -> not scanned
        q = MockJAMBQuestion.query.filter_by(subject_id=sid).first()
        assert q.topic == 'Hand-picked' and q.section == 'geometry'
        MockJAMBQuestion.query.filter_by(subject_id=sid).delete()
        db.session.delete(db.session.get(Subject, sid)); db.session.commit()
