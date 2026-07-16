"""Theme presets for the Website Builder.

A theme is a small token set (palette + font pairing + shape) applied to the
public site as CSS custom properties. Presets give a school a beautiful starting
point in one click; every token can then be overridden individually, so two
schools sharing a preset can still diverge. This is the mechanism that produces
visually distinct sites without per-school templates.
"""

# Curated presets: institutional, modern, bold, warm, minimal… Each is a full
# token set so a school looks finished the moment it picks one.
# Each preset pairs a display face for headings with a clean text face for body,
# both from Google Fonts (loaded on the public site). ``fonts`` lists the exact
# Google family specs so only the needed weights are requested.
PRESETS = {
    'emerald': {'label': 'Emerald (institutional)', 'primary': '#0d6a4e', 'accent': '#f2b705',
                'ink': '#14211c', 'surface': '#ffffff', 'muted': '#f4f7f5',
                'font_head': '"Playfair Display", Georgia, serif', 'font_body': '"Inter", system-ui, sans-serif',
                'fonts': ['Playfair+Display:wght@600;700;800', 'Inter:wght@400;500;600;700'],
                'radius': '10px', 'button': 'solid', 'shadow': 'soft', 'nav_style': 'classic'},
    'royal': {'label': 'Royal (classic)', 'primary': '#1e3a8a', 'accent': '#c9a227',
              'ink': '#111827', 'surface': '#ffffff', 'muted': '#f3f5fb',
              'font_head': '"Merriweather", Georgia, serif', 'font_body': '"Inter", system-ui, sans-serif',
              'fonts': ['Merriweather:wght@700;900', 'Inter:wght@400;500;600;700'],
              'radius': '6px', 'button': 'solid', 'shadow': 'soft', 'nav_style': 'classic'},
    'midnight': {'label': 'Midnight (bold contemporary)', 'primary': '#4f46e5', 'accent': '#22d3ee',
                 'ink': '#0b1020', 'surface': '#ffffff', 'muted': '#f5f6ff',
                 'font_head': '"Poppins", system-ui, sans-serif', 'font_body': '"Inter", system-ui, sans-serif',
                 'fonts': ['Poppins:wght@600;700;800', 'Inter:wght@400;500;600'],
                 'radius': '16px', 'button': 'gradient', 'shadow': 'strong', 'nav_style': 'floating'},
    'coral': {'label': 'Coral (warm modern)', 'primary': '#e2574c', 'accent': '#f6a609',
              'ink': '#2a1b18', 'surface': '#fffaf7', 'muted': '#fdeee8',
              'font_head': '"Poppins", system-ui, sans-serif', 'font_body': '"Nunito Sans", system-ui, sans-serif',
              'fonts': ['Poppins:wght@600;700;800', 'Nunito+Sans:wght@400;600;700'],
              'radius': '14px', 'button': 'solid', 'shadow': 'soft', 'nav_style': 'classic'},
    'slate': {'label': 'Slate (minimal)', 'primary': '#334155', 'accent': '#0ea5e9',
              'ink': '#0f172a', 'surface': '#ffffff', 'muted': '#f1f5f9',
              'font_head': '"Manrope", system-ui, sans-serif', 'font_body': '"Inter", system-ui, sans-serif',
              'fonts': ['Manrope:wght@600;700;800', 'Inter:wght@400;500;600'],
              'radius': '8px', 'button': 'outline', 'shadow': 'flat', 'nav_style': 'minimal'},
    'forest': {'label': 'Forest (natural)', 'primary': '#166534', 'accent': '#ca8a04',
               'ink': '#14261a', 'surface': '#ffffff', 'muted': '#eef4ee',
               'font_head': '"Lora", Georgia, serif', 'font_body': '"Inter", system-ui, sans-serif',
               'fonts': ['Lora:wght@600;700', 'Inter:wght@400;500;600;700'],
               'radius': '12px', 'button': 'solid', 'shadow': 'soft', 'nav_style': 'classic'},
    'plum': {'label': 'Plum (elegant)', 'primary': '#7c3aed', 'accent': '#ec4899',
             'ink': '#211427', 'surface': '#ffffff', 'muted': '#f7f2fb',
             'font_head': '"Playfair Display", Georgia, serif', 'font_body': '"Nunito Sans", system-ui, sans-serif',
             'fonts': ['Playfair+Display:wght@600;700;800', 'Nunito+Sans:wght@400;600;700'],
             'radius': '18px', 'button': 'gradient', 'shadow': 'strong', 'nav_style': 'floating'},
    'graphite': {'label': 'Graphite (corporate)', 'primary': '#0f766e', 'accent': '#f59e0b',
                 'ink': '#1c1917', 'surface': '#ffffff', 'muted': '#f5f5f4',
                 'font_head': '"Montserrat", system-ui, sans-serif', 'font_body': '"Open Sans", system-ui, sans-serif',
                 'fonts': ['Montserrat:wght@600;700;800', 'Open+Sans:wght@400;500;600;700'],
                 'radius': '6px', 'button': 'solid', 'shadow': 'flat', 'nav_style': 'minimal'},
}

_TOKENS = ('primary', 'accent', 'ink', 'surface', 'muted', 'font_head', 'font_body',
           'radius', 'button', 'shadow', 'nav_style')

_SHADOWS = {'flat': 'none', 'soft': '0 6px 24px rgba(0,0,0,.08)', 'strong': '0 18px 50px rgba(0,0,0,.18)'}


def resolve_theme(theme):
    """Merge a school's stored ``theme`` dict over its chosen preset (or the
    default), so every token is always populated for the renderer."""
    theme = theme or {}
    base = dict(PRESETS.get(theme.get('preset') or 'emerald', PRESETS['emerald']))
    merged = {k: theme.get(k) or base.get(k) for k in _TOKENS}
    merged['preset'] = theme.get('preset') or 'emerald'
    return merged


def theme_css_vars(theme):
    """The `:root{ --wb-*: … }` custom-property block for a resolved theme."""
    t = resolve_theme(theme)
    return (
        f"--wb-primary:{t['primary']};--wb-accent:{t['accent']};--wb-ink:{t['ink']};"
        f"--wb-surface:{t['surface']};--wb-muted:{t['muted']};"
        f"--wb-font-head:{t['font_head']};--wb-font-body:{t['font_body']};"
        f"--wb-radius:{t['radius']};--wb-shadow:{_SHADOWS.get(t['shadow'], _SHADOWS['soft'])};"
    )


def preset_choices():
    return [(k, v['label']) for k, v in PRESETS.items()]


def google_fonts_href(theme):
    """The Google Fonts stylesheet URL for a theme's preset (or None). Uses the
    preset's curated family list so only the needed weights are fetched. Allowed
    by the site CSP (style-src fonts.googleapis.com, font-src fonts.gstatic.com)."""
    theme = theme or {}
    preset = PRESETS.get(theme.get('preset') or 'emerald', PRESETS['emerald'])
    families = preset.get('fonts') or []
    if not families:
        return None
    query = '&'.join('family=' + f for f in families)
    return f'https://fonts.googleapis.com/css2?{query}&display=swap'
