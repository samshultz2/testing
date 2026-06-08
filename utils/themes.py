"""Selectable colour themes for the UI.

Each theme maps to a ``[data-theme="<key>"]`` block in static/css/style.css.
``swatch`` is the dot colour shown in the picker; ``dark`` flags dark-base themes.
"""

THEMES = [
    {'key': 'light',    'label': 'Emerald',  'swatch': '#0d6a4e', 'dark': False},
    {'key': 'ocean',    'label': 'Ocean',    'swatch': '#0e7490', 'dark': False},
    {'key': 'sunset',   'label': 'Sunset',   'swatch': '#c2410c', 'dark': False},
    {'key': 'berry',    'label': 'Berry',    'swatch': '#9d2463', 'dark': False},
    {'key': 'slate',    'label': 'Slate',    'swatch': '#475569', 'dark': False},
    {'key': 'dark',     'label': 'Dark',     'swatch': '#10b981', 'dark': True},
    {'key': 'midnight', 'label': 'Midnight', 'swatch': '#818cf8', 'dark': True},
]

THEME_KEYS = {t['key'] for t in THEMES}
DEFAULT_THEME = 'light'


def normalize_theme(value):
    """Return a valid theme key, falling back to the default."""
    return value if value in THEME_KEYS else DEFAULT_THEME
