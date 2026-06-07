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


def parse_user_agent(ua):
    """Return dict(browser, os, device_type, is_mobile) from a UA string."""
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
    }
