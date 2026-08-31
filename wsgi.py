"""
WSGI entry point for production servers (gunicorn, uWSGI, waitress).

    gunicorn -c gunicorn.conf.py wsgi:app

The application is built in app.py via the factory, which selects its config
from APP_ENV/FLASK_ENV. Set APP_ENV=production for a production deployment.
"""
from app import app  # the instance created by app.py's factory

__all__ = ['app']
