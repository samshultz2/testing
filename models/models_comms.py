"""
Communication models — message templates, broadcast campaigns and the
per-recipient delivery log.

Campaigns reach parents over SMS / WhatsApp (via a stored phone number) or Email
(via a stored parent email). Each recipient row carries its personalised body and
delivery status, so schools keep a full, auditable communication history.
"""
from models.models import db, local_now


class CommAttachment(db.Model):
    """An uploaded file attached to an announcement or an email campaign. Stored on
    disk under the tenant's upload folder; only metadata lives here."""
    __tablename__ = 'comm_attachments'

    id = db.Column(db.Integer, primary_key=True)
    stored_name = db.Column(db.String(80), nullable=False)     # on-disk filename
    original_name = db.Column(db.String(200), nullable=False)  # what the user sees
    content_type = db.Column(db.String(100))
    size = db.Column(db.Integer, default=0)                    # bytes
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)

    @property
    def human_size(self):
        n = self.size or 0
        for unit in ('B', 'KB', 'MB', 'GB'):
            if n < 1024 or unit == 'GB':
                return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
            n /= 1024.0

    def __repr__(self):
        return f'<CommAttachment {self.original_name!r}>'


class Announcement(db.Model):
    """An in-app school notice shown on the dashboard."""
    __tablename__ = 'announcements'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    body = db.Column(db.Text)
    audience = db.Column(db.String(20), default='All')   # All/Staff/Students/Parents
    category = db.Column(db.String(20), default='Info')   # Info/Important/Event
    is_pinned = db.Column(db.Boolean, default=False)
    needs_ack = db.Column(db.Boolean, default=False)   # require staff to acknowledge
    attachment_id = db.Column(db.Integer, db.ForeignKey('comm_attachments.id'))
    starts_on = db.Column(db.Date)
    ends_on = db.Column(db.Date)
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)

    @property
    def is_active(self):
        from datetime import date
        today = date.today()
        if self.starts_on and today < self.starts_on:
            return False
        if self.ends_on and today > self.ends_on:
            return False
        return True

    def __repr__(self):
        return f'<Announcement {self.title!r}>'


class AnnouncementAck(db.Model):
    """Records that a user has acknowledged a (needs_ack) announcement."""
    __tablename__ = 'announcement_acks'

    id = db.Column(db.Integer, primary_key=True)
    announcement_id = db.Column(db.Integer, db.ForeignKey('announcements.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    acked_at = db.Column(db.DateTime, default=local_now)

    __table_args__ = (db.UniqueConstraint('announcement_id', 'user_id',
                                          name='uq_ann_ack'),)


class Notification(db.Model):
    """An in-app notification for a staff user (the header bell).

    Addressed either to one user (``user_id``) or broadcast to a role
    (``role``); ``role='admin'`` reaches every admin. Cheap to create via
    ``utils.notify.notify`` and read back per user.
    """
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    role = db.Column(db.String(20), nullable=True, index=True)   # broadcast to a role
    title = db.Column(db.String(150), nullable=False)
    body = db.Column(db.Text)
    url = db.Column(db.String(300))
    category = db.Column(db.String(20), default='info')   # info/success/warning/error
    is_read = db.Column(db.Boolean, default=False, index=True)
    # When this bell notice was delivered by an in-app campaign, links back to the
    # campaign recipient so reading it counts as a campaign read-receipt.
    origin_recipient_id = db.Column(db.Integer, db.ForeignKey('message_recipients.id'))
    created_at = db.Column(db.DateTime, default=local_now, index=True)

    def to_dict(self):
        return {
            'id': self.id, 'title': self.title, 'body': self.body or '',
            'url': self.url, 'category': self.category, 'is_read': bool(self.is_read),
            'when': self.created_at.strftime('%d %b %Y %H:%M') if self.created_at else '',
        }

    def __repr__(self):
        return f'<Notification {self.title!r}>'


class RecipientGroup(db.Model):
    """A saved recipient selection (a comms recipient spec) that a user can reload
    in the composer instead of rebuilding the same audience each time."""
    __tablename__ = 'recipient_groups'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    spec = db.Column(db.Text, nullable=False)        # JSON recipient spec
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))   # owning branch
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)

    def spec_dict(self):
        import json
        try:
            return json.loads(self.spec or '{}')
        except (ValueError, TypeError):
            return {}

    def __repr__(self):
        return f'<RecipientGroup {self.name!r}>'


class MessageTemplate(db.Model):
    """A reusable message body with {placeholders}."""
    __tablename__ = 'message_templates'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(40))          # Fees, Attendance, General, Event…
    body = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    is_favorite = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=local_now)

    def __repr__(self):
        return f'<MessageTemplate {self.name}>'


class Message(db.Model):
    """A broadcast campaign sent to a chosen audience of parents."""
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120))
    body = db.Column(db.Text, nullable=False)        # template (pre-personalisation)
    channel = db.Column(db.String(20), default='WhatsApp')  # WhatsApp / SMS
    audience = db.Column(db.String(40))              # all / class / students / defaulters
    audience_label = db.Column(db.String(120))       # human description, e.g. "JSS1 Rose"
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'), nullable=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))   # owning branch (scoping)
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)
    recipient_count = db.Column(db.Integer, default=0)
    sent_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(15), default='Draft')   # Draft/Scheduled/Sending/Sent
    scheduled_at = db.Column(db.DateTime)                 # when to auto-send (gateway)
    attachment_id = db.Column(db.Integer, db.ForeignKey('comm_attachments.id'))  # email only

    term = db.relationship('Term')
    recipients = db.relationship('MessageRecipient', backref='message',
                                 lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Message {self.id} {self.title!r}>'


class MessageRecipient(db.Model):
    """One parent target of a campaign, with the personalised body + status."""
    __tablename__ = 'message_recipients'

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('messages.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=True)
    parent_name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))               # destination for Email-channel sends
    body = db.Column(db.Text)                       # personalised message
    status = db.Column(db.String(15), default='Pending')  # Pending / Sent / Failed
    sent_at = db.Column(db.DateTime)
    read_at = db.Column(db.DateTime)      # when the recipient opened/read it
    error = db.Column(db.Text)            # provider error on a failed gateway send
    created_at = db.Column(db.DateTime, default=local_now)

    student = db.relationship('Student')

    def __repr__(self):
        return f'<MessageRecipient {self.phone} {self.status}>'
