"""
CSRF Protection for PosyHub - Disabled
"""
from functools import wraps


def csrf_protect(f):
    """CSRF protection disabled"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function
