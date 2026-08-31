"""Internal staff-messaging service.

Thin, side-effect-honest helpers over the Conversation / ConversationMember /
ChatMessage models. Everything is keyed on a ``User`` id; callers resolve the
current user first. Kept free of request/session state so a route or a job can
drive it.
"""
from __future__ import annotations


def _now():
    # Match the models' created_at clock (local_now) so read watermarks compare
    # correctly against message timestamps.
    from models.models import local_now
    return local_now()


# --- creating / finding conversations ---------------------------------------
def get_or_create_direct(user_id, other_id, branch_id=None):
    """The 1:1 conversation between two users, created on first use. Returns the
    Conversation (or None if the two ids are the same)."""
    from models import db, Conversation, ConversationMember
    if not other_id or int(other_id) == int(user_id):
        return None
    # A direct conversation is the one whose exact member set is {user, other}.
    mine = {c.conversation_id for c in ConversationMember.query.filter_by(user_id=user_id)}
    theirs = {c.conversation_id for c in ConversationMember.query.filter_by(user_id=other_id)}
    for cid in mine & theirs:
        conv = db.session.get(Conversation, cid)
        if conv and conv.kind == 'direct' and conv.members.count() == 2:
            return conv
    conv = Conversation(kind='direct', branch_id=branch_id, created_by=user_id)
    db.session.add(conv)
    db.session.flush()
    db.session.add(ConversationMember(conversation_id=conv.id, user_id=user_id))
    db.session.add(ConversationMember(conversation_id=conv.id, user_id=int(other_id)))
    db.session.commit()
    return conv


def create_group(creator_id, member_ids, title, branch_id=None):
    """Create a group conversation. ``member_ids`` need not include the creator."""
    from models import db, Conversation, ConversationMember
    ids = {int(x) for x in member_ids if x} | {int(creator_id)}
    if len(ids) < 2:
        return None
    conv = Conversation(kind='group', title=(title or 'Group').strip()[:120],
                        branch_id=branch_id, created_by=creator_id)
    db.session.add(conv)
    db.session.flush()
    for uid in ids:
        db.session.add(ConversationMember(conversation_id=conv.id, user_id=uid))
    db.session.commit()
    return conv


def is_member(conv_id, user_id):
    from models import ConversationMember
    return ConversationMember.query.filter_by(
        conversation_id=conv_id, user_id=user_id).first() is not None


# --- posting / reading ------------------------------------------------------
def post_message(conv_id, sender_id, body, attachment_id=None):
    """Append a message (must be a member). Returns the ChatMessage or None."""
    from models import db, Conversation, ChatMessage
    body = (body or '').strip()
    if not (body or attachment_id) or not is_member(conv_id, sender_id):
        return None
    m = ChatMessage(conversation_id=conv_id, sender_id=sender_id, body=body or None,
                    attachment_id=attachment_id)
    db.session.add(m)
    conv = db.session.get(Conversation, conv_id)
    if conv:
        conv.last_at = _now()
    db.session.flush()
    mark_read(conv_id, sender_id)         # sender has read their own message
    db.session.commit()
    return m


def mark_read(conv_id, user_id):
    from models import db, ConversationMember
    mem = ConversationMember.query.filter_by(conversation_id=conv_id, user_id=user_id).first()
    if mem:
        mem.last_read_at = _now()
        db.session.commit()
    return mem


def _display_name(user):
    return (getattr(user, 'full_name', None) or getattr(user, 'username', None)
            or f'User {getattr(user, "id", "?")}')


def conversation_title(conv, user_id):
    """Group title, or (for a direct chat) the *other* member's name."""
    from models import ConversationMember
    if conv.kind == 'group':
        return conv.title or 'Group'
    other = (ConversationMember.query.filter(
        ConversationMember.conversation_id == conv.id,
        ConversationMember.user_id != user_id).first())
    return _display_name(other.user) if other and other.user else 'Direct message'


def unread_count(conv, user_id):
    from models import ChatMessage, ConversationMember
    mem = ConversationMember.query.filter_by(conversation_id=conv.id, user_id=user_id).first()
    if not mem:
        return 0
    q = ChatMessage.query.filter(ChatMessage.conversation_id == conv.id,
                                 ChatMessage.sender_id != user_id)
    if mem.last_read_at:
        q = q.filter(ChatMessage.created_at > mem.last_read_at)
    return q.count()


def conversations_for(user_id):
    """Every conversation the user belongs to, most-recent first, with the last
    message snippet and their unread count."""
    from models import db, Conversation, ConversationMember, ChatMessage
    cids = [m.conversation_id for m in ConversationMember.query.filter_by(user_id=user_id)]
    if not cids:
        return []
    convs = (Conversation.query.filter(Conversation.id.in_(cids))
             .order_by(Conversation.last_at.desc()).all())
    out = []
    for c in convs:
        last = (ChatMessage.query.filter_by(conversation_id=c.id)
                .order_by(ChatMessage.created_at.desc()).first())
        out.append({
            'id': c.id, 'kind': c.kind, 'title': conversation_title(c, user_id),
            'last': (last.body or ('📎 attachment' if last.attachment_id else '')) if last else '',
            'last_at': c.last_at.strftime('%d %b %H:%M') if c.last_at else '',
            'unread': unread_count(c, user_id),
        })
    return out


def total_unread(user_id):
    from models import Conversation, ConversationMember
    cids = [m.conversation_id for m in ConversationMember.query.filter_by(user_id=user_id)]
    total = 0
    for c in Conversation.query.filter(Conversation.id.in_(cids or [-1])).all():
        total += unread_count(c, user_id)
    return total
