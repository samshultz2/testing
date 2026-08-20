"""The students export can include the external-exam identity records:
NIN, JAMB profile code, JAMB registration number, WAEC registration number.
"""
import json
from config import Config
from tests.conftest import login_token


def test_export_includes_exam_identity_fields(app):
    from models import db, Student
    with app.app_context():
        s = Student(student_id='EXP-NIN', first_name='Ex', surname='Port',
                    gender='Male', is_active=True, nin='12345678901',
                    jamb_reg_number='JMB-999', jamb_profile_code='PC-777',
                    waec_reg_number='WEC-555')
        db.session.add(s); db.session.commit()
        sid = s.id
    try:
        c = app.test_client()
        c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
        fields = ['student_id', 'nin', 'jamb_profile_code', 'jamb_reg_number', 'waec_reg_number']
        r = c.get('/students/export', query_string={
            'format': 'csv', 'fields': json.dumps(fields),
            'student_ids': json.dumps([sid])})
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert 'NIN' in body and 'JAMB Profile Code' in body
        assert 'JAMB Reg Number' in body and 'WAEC Reg Number' in body
        assert '12345678901' in body and 'JMB-999' in body
        assert 'PC-777' in body and 'WEC-555' in body
    finally:
        with app.app_context():
            o = db.session.get(Student, sid)
            if o:
                db.session.delete(o); db.session.commit()
