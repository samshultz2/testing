"""Shared SPA helper: render the React shell for a normal navigation, but return
the same payload as JSON when the React client asks for it (so in-section
navigation, filtering and post-action refreshes happen with no full reload)."""
from flask import request, jsonify, render_template


def current_section_perms():
    """Write/read permissions for the module the current request belongs to, so
    every React section can hide actions the user may not perform.

    Returns ``{module, level, write, read_only, subs:{sub:{level,write}}}``.
    ``write`` is True only when the user holds 'edit' on the module (or the
    relevant sub-section) AND is not globally view-only. Admins get write.
    """
    try:
        from utils.access_control import (BLUEPRINT_MODULE, MODULE_SUBSECTIONS,
                                          module_level, subsection_level, is_read_only)
        ro = bool(is_read_only())
        bp = (request.endpoint or '').split('.')[0]
        mod = BLUEPRINT_MODULE.get(bp)
        if not mod:
            return {'module': None, 'level': None, 'write': not ro,
                    'read_only': ro, 'subs': {}}
        lvl = module_level(mod)
        subs = {}
        for sub in MODULE_SUBSECTIONS.get(mod, {}):
            slvl = subsection_level(mod, sub)
            subs[sub] = {'level': slvl, 'write': slvl == 'edit' and not ro}
        return {'module': mod, 'level': lvl, 'write': (lvl == 'edit') and not ro,
                'read_only': ro, 'subs': subs}
    except Exception:
        # Never let a permissions hiccup break a page render — fail open to the
        # server-side gate (which still blocks the actual write).
        return {'module': None, 'level': None, 'write': True, 'read_only': False,
                'subs': {}}


def wants_json():
    if request.headers.get('X-Requested-With') == 'fetch' or request.is_json:
        return True
    accept = request.headers.get('Accept', '')
    return 'application/json' in accept and 'text/html' not in accept


def render_or_json(template, var, payload):
    # Every React section payload gets a `perms` block so the client can hide
    # actions the user isn't allowed to perform (the server still enforces the
    # write). This is the single choke point every section render passes
    # through — sections with a bespoke `_render` (library, admissions,
    # promotion, events, sales, …) get it here without each having to opt in.
    if isinstance(payload, dict):
        payload.setdefault('perms', current_section_perms())
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
        # Every section gets a `perms` block so the React client can hide
        # actions the user isn't allowed to perform (the server still enforces).
        if isinstance(payload, dict):
            payload.setdefault('perms', current_section_perms())
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
