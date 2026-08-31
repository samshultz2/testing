"""Internal staff messaging — one-to-one and group conversations between users.

Distinct from the broadcast ``Message`` campaigns (which target parents/students):
this is staff talking to staff. A conversation has members and a stream of
``ChatMessage`` rows; each member keeps a ``last_read_at`` watermark for unread
counts.
"""
from models.models import db, local_now


class Conversation(db.Model):
    __tablename__ = 'chat_conversations'

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(10), default='direct')     # 'direct' | 'group'
    title = db.Column(db.String(120))                     # group name (direct = derived)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))   # owning branch
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=local_now)
    last_at = db.Column(db.DateTime, default=local_now, index=True)   # last activity

    members = db.relationship('ConversationMember', backref='conversation',
                              lazy='dynamic', cascade='all, delete-orphan')
    messages = db.relationship('ChatMessage', backref='conversation',
                               lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Conversation {self.id} {self.kind}>'


class ConversationMember(db.Model):
    __tablename__ = 'chat_members'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('chat_conversations.id'),
                                nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    last_read_at = db.Column(db.DateTime)      # watermark for unread counts
    added_at = db.Column(db.DateTime, default=local_now)

    user = db.relationship('User')

    __table_args__ = (db.UniqueConstraint('conversation_id', 'user_id',
                                          name='uq_chat_member'),)


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('chat_conversations.id'),
                                nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    body = db.Column(db.Text)
    attachment_id = db.Column(db.Integer, db.ForeignKey('comm_attachments.id'))
    created_at = db.Column(db.DateTime, default=local_now, index=True)

    sender = db.relationship('User')

    def __repr__(self):
        return f'<ChatMessage {self.id} conv={self.conversation_id}>'
