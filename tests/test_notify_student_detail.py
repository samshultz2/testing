"""Student-change notifications carry detail: whose record, what field changed
(old → new) and who did it."""
from models import db, Student
from utils.notify import notify_student_change


def test_update_notification_has_who_what_and_actor(app):
    with app.app_context():
        s = Student(student_id='NOTIF-1', first_name='John', surname='Doe',
                    gender='Male', is_active=True)
        db.session.add(s); db.session.commit()
        n = notify_student_change(
            'update', student=s,
            changes='JAMB target: (empty) → "250"; Stream: "Science" → "Arts"',
            actor='Mrs Bello', url='/students/x')
        assert n is not None
        assert n.title == 'Student updated'
        # WHO the record is (name + id), WHAT changed, and WHO did it.
        assert s.full_name in n.body and '(NOTIF-1)' in n.body
        assert 'JAMB target: (empty) → "250"' in n.body
        assert 'Stream: "Science" → "Arts"' in n.body
        assert 'by Mrs Bello' in n.body


def test_create_and_delete_carry_actor(app):
    with app.app_context():
        s = Student(student_id='NOTIF-2', first_name='Ada', surname='Obi',
                    gender='Female', is_active=True)
        db.session.add(s); db.session.commit()
        nc = notify_student_change('create', student=s, actor='Mr Ade')
        assert nc and s.full_name in nc.body and '(NOTIF-2)' in nc.body and 'by Mr Ade' in nc.body
        nd = notify_student_change('delete', detail='Ada Obi (NOTIF-2)', actor='Mr Ade')
        assert nd and 'by Mr Ade' in nd.body
