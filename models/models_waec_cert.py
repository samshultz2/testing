"""WAEC result generator — persisted templates, presets and issued-cert records.

These back the template-management, reusable-preset and QR-verification features
of the WAEC result generator (see utils.waec_result_gen). The visual layouts
themselves are code (the six canvas designs); a ``WAECCertTemplate`` row records
which layout + options a school uses, and for which exam year / branch, so
historical designs are preserved and new yearly designs never overwrite old ones.
"""
import json
import secrets
from datetime import datetime

from models.models import db, local_now


class WAECCertTemplate(db.Model):
    """A managed template: a named binding of a code layout + saved options to an
    exam type / year / branch, with status, default flag and version history."""
    __tablename__ = 'waec_cert_templates'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(400))
    base_layout = db.Column(db.String(30), nullable=False, default='prestige')
    exam_type = db.Column(db.String(20), default='waec')
    year = db.Column(db.Integer)                      # None = applies to any year
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))  # None = all branches
    is_default = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='active')   # active | archived
    version = db.Column(db.Integer, default=1)
    options_json = db.Column(db.Text)                # {preset, components:[...], config:{...}}
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

    def options(self):
        try:
            return json.loads(self.options_json) if self.options_json else {}
        except (TypeError, ValueError):
            return {}


class WAECCertPreset(db.Model):
    """A reusable component selection (what to include) — no result data."""
    __tablename__ = 'waec_cert_presets'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    components_json = db.Column(db.Text)             # ["school_name", "grades", ...]
    config_json = db.Column(db.Text)                # {"student_photo": {"size": "medium"}}
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)

    def components(self):
        try:
            return json.loads(self.components_json) if self.components_json else []
        except (TypeError, ValueError):
            return []

    def config(self):
        try:
            return json.loads(self.config_json) if self.config_json else {}
        except (TypeError, ValueError):
            return {}


class WAECCertIssue(db.Model):
    """A record of a generated result document, addressable by a public
    verification code (encoded in the optional QR component)."""
    __tablename__ = 'waec_cert_issues'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(24), unique=True, index=True, nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), index=True)
    exam_year = db.Column(db.Integer)
    template_key = db.Column(db.String(30))
    output_format = db.Column(db.String(8))
    components_summary = db.Column(db.String(400))
    issued_by = db.Column(db.String(100))
    issued_at = db.Column(db.DateTime, default=local_now)
    revoked = db.Column(db.Boolean, default=False)

    @staticmethod
    def new_code():
        # short, unambiguous, URL-safe
        alphabet = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'
        return 'WR-' + ''.join(secrets.choice(alphabet) for _ in range(8))
