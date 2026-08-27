"""Admissions form: the origin/health fields save, and a passport photo can be
uploaded (stored in its own table) and served back behind login."""
import base64
import io
import itertools
from PIL import Image
from config import Config
from models import db, Applicant, ApplicantPhoto
from tests.conftest import login_token, auth_csrf

_SEQ = itertools.count()


def _data_url():
    im = Image.new('RGB', (200, 260), (90, 120, 200))
    b = io.BytesIO(); im.save(b, 'PNG')
    return 'data:image/png;base64,' + base64.b64encode(b.getvalue()).decode()


def test_new_fields_and_photo(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    tag = next(_SEQ)
    r = c.post('/admissions/applicants/add', data={
        '_csrf_token': auth_csrf(c),
        'first_name': f'Ada{tag}', 'surname': 'Origin',
        'country': 'Nigeria', 'state_of_origin': 'Edo', 'lga': 'Oredo',
        'father_occupation': 'Engineer', 'languages_spoken': 'Edo, English',
        'blood_group': 'O+', 'genotype': 'AA',
        'photo_data': _data_url(),
    }, follow_redirects=False)
    assert r.status_code in (200, 302)

    with app.app_context():
        a = Applicant.query.filter_by(first_name=f'Ada{tag}').first()
        assert a is not None
        assert a.state_of_origin == 'Edo' and a.lga == 'Oredo'
        assert a.father_occupation == 'Engineer' and a.blood_group == 'O+' and a.genotype == 'AA'
        assert a.languages_spoken == 'Edo, English'
        assert ApplicantPhoto.query.filter_by(applicant_id=a.id).count() == 1
        aid = a.id

    # The photo is served back (login + branch scoped) as an image.
    r = c.get(f'/admissions/applicants/{aid}/photo')
    assert r.status_code == 200 and r.mimetype.startswith('image/')


def test_blank_form_bw_differs_from_colour(app):
    from utils.applicant_export import applicant_blank_pdf
    school = {'name': 'Test School'}
    colour = applicant_blank_pdf(school, bw=False)
    bw = applicant_blank_pdf(school, bw=True)
    assert colour[:4] == b'%PDF' and bw[:4] == b'%PDF'
    assert colour != bw                          # the B&W variant is genuinely different
