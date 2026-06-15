"""Shared SPA helper: render the React shell for a normal navigation, but return
the same payload as JSON when the React client asks for it (so in-section
navigation, filtering and post-action refreshes happen with no full reload)."""
from flask import request, jsonify, render_template


def wants_json():
    if request.headers.get('X-Requested-With') == 'fetch' or request.is_json:
        return True
    accept = request.headers.get('Accept', '')
    return 'application/json' in accept and 'text/html' not in accept


def render_or_json(template, var, payload):
    if wants_json():
        return jsonify(payload)
    return render_template(template, **{var: payload})
