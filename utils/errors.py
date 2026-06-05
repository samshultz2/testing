"""Friendly error pages."""
from flask import render_template, request, jsonify


def _wants_json():
    best = request.accept_mimetypes.best_match(['application/json', 'text/html'])
    return best == 'application/json' or request.path.startswith('/api/')


def register_error_handlers(app):
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
        return render_template('errors/error.html', code=404, title='Not Found',
                               message="That page doesn't exist."), 404

    @app.errorhandler(500)
    def server_error(e):
        if _wants_json():
            return jsonify(error='Server error'), 500
        return render_template('errors/error.html', code=500, title='Something went wrong',
                               message='An unexpected error occurred. Please try again.'), 500
