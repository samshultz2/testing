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


def section_responders(template, json_var, default_endpoint, enrich=None):
    """Build the standard SPA response helpers a converted section blueprint
    needs, removing the ~30 lines of boilerplate each one used to copy:

        _wants_json, _render, _ok, _err = section_responders(
            'settings/app.html', 'settings_json', 'settings.index')

    * ``_render(payload)``   → the shell HTML, or the payload as JSON for fetch.
    * ``_ok(msg, url, **x)`` → ``{ok: True, ...}`` for fetch, else flash+redirect.
    * ``_err(msg, url, n)``  → ``{ok: False, error}`` + status for fetch, else
                               flash+redirect.

    ``enrich(payload)`` (optional) mutates the payload before rendering — used by
    sections that always inject shared nav URLs / flags.
    """
    from flask import flash, redirect, url_for

    def _render(payload):
        if enrich:
            enrich(payload)
        return render_or_json(template, json_var, payload)

    def _ok(message, redirect_url=None, **extra):
        if wants_json():
            return jsonify({'ok': True, 'message': message, 'redirect': redirect_url, **extra})
        flash(message, 'success')
        return redirect(redirect_url or url_for(default_endpoint))

    def _err(message, redirect_url=None, status=400):
        if wants_json():
            return jsonify({'ok': False, 'error': message}), status
        flash(message, 'error')
        return redirect(redirect_url or url_for(default_endpoint))

    return wants_json, _render, _ok, _err
