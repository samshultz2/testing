"""Tenant-facing support tickets: a school's admins raise and follow up support
conversations with the platform operator. Tickets live in the control plane so
the operator sees them in the platform console (routes.platform)."""
from functools import wraps

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, session, abort)

from utils import tenancy
from utils.tenant_runtime import current_tenant
from utils.access_control import is_admin

support_bp = Blueprint('support', __name__, url_prefix='/support')


def _school_admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('logged_in') or not is_admin():
            return redirect(url_for('auth.login'))
        if current_tenant() is None:
            abort(404)
        return f(*args, **kwargs)
    return wrapper


@support_bp.route('/')
@_school_admin_required
def index():
    sub = current_tenant().subdomain
    tickets = tenancy.list_tickets(subdomain=sub)
    return render_template('support/index.html', tickets=tickets)


@support_bp.route('/new', methods=['POST'])
@_school_admin_required
def new():
    sub = current_tenant().subdomain
    subject = (request.form.get('subject') or '').strip()
    body = (request.form.get('body') or '').strip()
    if not subject or not body:
        flash('Add a subject and a message.', 'error')
        return redirect(url_for('support.index'))
    tid = tenancy.create_ticket(sub, subject, body,
                                created_by=session.get('username') or 'admin',
                                priority=(request.form.get('priority') or 'normal'),
                                is_staff=False)
    flash('Support ticket opened — we’ll get back to you here.', 'success')
    return redirect(url_for('support.thread', ticket_id=tid))


@support_bp.route('/<int:ticket_id>')
@_school_admin_required
def thread(ticket_id):
    sub = current_tenant().subdomain
    ticket, messages = tenancy.get_ticket(ticket_id, subdomain=sub)
    if ticket is None:
        abort(404)
    return render_template('support/thread.html', ticket=ticket, messages=messages)


@support_bp.route('/<int:ticket_id>/reply', methods=['POST'])
@_school_admin_required
def reply(ticket_id):
    sub = current_tenant().subdomain
    ticket, _ = tenancy.get_ticket(ticket_id, subdomain=sub)
    if ticket is None:
        abort(404)
    body = (request.form.get('body') or '').strip()
    if body:
        tenancy.add_ticket_message(ticket_id, body,
                                   author=session.get('username') or 'admin', is_staff=False)
    return redirect(url_for('support.thread', ticket_id=ticket_id))
