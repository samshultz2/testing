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


def test_export_includes_neco_and_waec_pin_fields(app):
    import fitz
    from models import db, Student
    with app.app_context():
        s = Student(student_id='EXP-NECO', first_name='Ne', surname='Coexport', gender='Female', is_active=True,
                    neco_reg_number='NEC-321', neco_epin='TOK-654', waec_reg_number='WEC-111',
                    serial_number='SER-222', waec_epin='PIN-333')
        db.session.add(s); db.session.commit()
        sid = s.id
    try:
        c = app.test_client()
        c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
        fields = ['name', 'waec_reg_number', 'serial_number', 'waec_epin', 'neco_reg_number', 'neco_epin']
        q = {'fields': json.dumps(fields), 'student_ids': json.dumps([sid])}
        body = c.get('/students/export', query_string=dict(q, format='csv')).get_data(as_text=True)
        for want in ('NECO Reg Number', 'NECO Token / e-PIN', 'WAEC Serial Number', 'WAEC e-PIN',
                     'NEC-321', 'TOK-654', 'SER-222', 'PIN-333'):
            assert want in body, want
        pdf = c.get('/students/export', query_string=dict(q, format='pdf'))
        with fitz.open(stream=pdf.data, filetype='pdf') as d:
            txt = ' '.join(p.get_text() for p in d)
        assert 'NECO TOKEN' in txt.upper() and 'TOK-654' in txt and 'NEC-321' in txt
    finally:
        with app.app_context():
            o = db.session.get(Student, sid)
            if o:
                db.session.delete(o); db.session.commit()
