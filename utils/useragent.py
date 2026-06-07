"""Tiny dependency-free User-Agent parser for CBT device fingerprinting.

Good enough to tell investigators the browser, OS and device class behind an
exam login. Not a substitute for a full UA database, but needs no network or
third-party package.
"""
import re


def _first(patterns, ua):
    for label, rx in patterns:
        if re.search(rx, ua, re.I):
            return label
    return None


_BROWSERS = [
    ('Edge', r'edg(e|a|ios)?/'),
    ('Opera', r'opr/|opera'),
    ('Samsung Internet', r'samsungbrowser'),
    ('Chrome', r'chrome|crios|chromium'),
    ('Firefox', r'firefox|fxios'),
    ('Safari', r'safari'),
    ('Internet Explorer', r'msie|trident'),
]

_OS = [
    ('Android', r'android'),
    ('iOS', r'iphone|ipad|ipod'),
    ('Windows', r'windows nt'),
    ('macOS', r'mac os x|macintosh'),
    ('Chrome OS', r'cros'),
    ('Linux', r'linux'),
]


def device_model(ua):
    """Best-effort device model from a UA string (e.g. 'Redmi 13C', 'SM-G991B').

    Modern Chrome on Android sends a 'reduced' UA where the model is just 'K',
    so the reliable source is UA Client Hints (captured client-side). This is a
    fallback for older/other browsers.
    """
    ua = ua or ''
    if re.search(r'ipad', ua, re.I):
        return 'iPad'
    if re.search(r'iphone', ua, re.I):
        return 'iPhone'
    m = re.search(r'android[^;]*;\s*([^;)]+?)\s*(?:build/|[)])', ua, re.I)
    if m:
        model = m.group(1).strip()
        if model and model.lower() not in ('wv', 'k'):
            return model
    return None


def parse_user_agent(ua):
    """Return dict(browser, os, device_type, is_mobile, model) from a UA string."""
    ua = ua or ''
    browser = _first(_BROWSERS, ua) or 'Unknown'
    os_name = _first(_OS, ua) or 'Unknown'
    is_tablet = bool(re.search(r'ipad|tablet|(android(?!.*mobile))', ua, re.I))
    is_mobile = bool(re.search(r'mobile|iphone|ipod|android.*mobile|windows phone', ua, re.I))
    if is_tablet:
        device_type = 'Tablet'
    elif is_mobile:
        device_type = 'Mobile'
    else:
        device_type = 'Desktop'
    return {
        'browser': browser,
        'os': os_name,
        'device_type': device_type,
        'is_mobile': is_mobile or is_tablet,
        'model': device_model(ua),
    }
