"""Background jobs — a tiny per-tenant work queue for long-running admin tasks
(e.g. a bulk analytics recompute). Rows are drained by the in-process scheduler
tick on the bound tenant DB. Gated by the ASYNC_JOBS feature flag; when it is
off nothing writes here and callers run their work synchronously as before.
"""
import json

from models.models import db, local_now


class BackgroundJob(db.Model):
    __tablename__ = 'background_jobs'

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(50), nullable=False, index=True)
    # queued → running → done | failed
    status = db.Column(db.String(12), nullable=False, default='queued', index=True)
    params = db.Column(db.Text)               # JSON args for the handler
    progress = db.Column(db.Integer, default=0)
    total = db.Column(db.Integer, default=0)
    message = db.Column(db.Text)              # failure reason / status note
    result = db.Column(db.Text)              # JSON result summary
    created_by = db.Column(db.String(100))
    branch_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=local_now)
    started_at = db.Column(db.DateTime)
    finished_at = db.Column(db.DateTime)

    def as_dict(self):
        return {
            'id': self.id, 'kind': self.kind, 'status': self.status,
            'progress': self.progress or 0, 'total': self.total or 0,
            'message': self.message,
            'result': (json.loads(self.result) if self.result else None),
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
        }

    def __repr__(self):
        return f'<BackgroundJob {self.kind} {self.status}>'
