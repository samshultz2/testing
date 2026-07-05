"""Friendly error pages + structured error tracking."""
import traceback

from flask import render_template, request, jsonify, session, got_request_exception


def _wants_json():
    # SPA fetches (in-section React nav) expect JSON; the soft-nav and normal
    # browsing expect the HTML error page.
    if request.headers.get('X-Requested-With') == 'fetch' or request.is_json:
        return True
    if request.path.startswith('/api/'):
        return True
    best = request.accept_mimetypes.best_match(['application/json', 'text/html'])
    return best == 'application/json'


def _current_user():
    return (session.get('username') or session.get('parent_student_id')
            or session.get('cbt_student_id') or 'anonymous')


def register_error_handlers(app):
    # Log EVERY unhandled exception with full context, regardless of which error
    # page is rendered (works whether or not DEBUG re-raises).
    def _log_exception(sender, exception, **extra):
        try:
            from utils.error_tracking import record_error
            record_error('server', f'{type(exception).__name__}: {exception}',
                         where=f'{request.method} {request.path}',
                         user=_current_user(), detail=traceback.format_exc())
        except Exception:
            pass
    got_request_exception.connect(_log_exception, app)

    @app.errorhandler(400)
    def bad_request(e):
        msg = getattr(e, 'description', 'Bad request.')
        if _wants_json():
            return jsonify(error=msg), 400
        return render_template('errors/error.html', code=400, title='Bad Request', message=msg), 400

    @app.errorhandler(403)
    def forbidden(e):
        if _wants_json():
            return jsonify(error='Forbidden'), 403
        return render_template('errors/error.html', code=403, title='Forbidden',
                               message="You don't have permission to do that."), 403

    @app.errorhandler(404)
    def not_found(e):
        if _wants_json():
            return jsonify(error='Not found'), 404
        return render_template('errors/error.html', code=404, title='Page Not Found',
                               message="That page doesn't exist or may have moved."), 404

    @app.errorhandler(413)
    def too_large(e):
        from flask import current_app
        cap = current_app.config.get('MAX_CONTENT_LENGTH')
        limit = f'{cap // (1024 * 1024)} MB' if cap else 'the allowed size'
        msg = f'That upload is too large. Please keep files under {limit}.'
        if _wants_json():
            return jsonify(error=msg), 413
        return render_template('errors/error.html', code=413, title='Upload Too Large',
                               message=msg), 413

    @app.errorhandler(429)
    def too_many(e):
        msg = getattr(e, 'description', 'Too many requests. Please slow down and try again shortly.')
        if _wants_json():
            return jsonify(error=msg), 429
        return render_template('errors/error.html', code=429, title='Too Many Requests',
                               message=msg), 429

    @app.errorhandler(500)
    def server_error(e):
        if _wants_json():
            return jsonify(error='Server error'), 500
        return render_template('errors/error.html', code=500, title='Something went wrong',
                               message='An unexpected error occurred. The team has been notified. '
                                       'Please try again.'), 500
