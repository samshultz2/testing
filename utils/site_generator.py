"""One-click website generation for the Website Builder.

Builds a complete, multi-page site — theme, pages, sections and copy — in a
single step, so a school admin who can't design gets a finished, good-looking
site to start from. The result is deterministically *seeded by the school's own
identity*, so different schools get genuinely different looks (theme, section
layouts, variant choices and ordering) rather than one shared template. Because
it produces ordinary ``SitePage``/``SiteSettings`` rows, everything it makes is
fully editable afterwards in the normal editor.

Copy is written from the school's own branding (name, motto). When the AI
assistant is configured it can polish a few key sections; without it, sensible
branded copy is used — the button always works.
"""
import hashlib
import random

from models import db, SiteSettings, SitePage
from utils import site_blocks
from utils.site_themes import PRESETS


def _rng(salt=''):
    from models import SchoolSettings
    name = (SchoolSettings.get('school_name', '') or 'School')
    seed = int(hashlib.sha256(f'{name}|{salt}'.encode('utf-8')).hexdigest(), 16)
    return random.Random(seed), name


def _branding():
    from utils.site_data import public_context
    return public_context()['branding']


def _block(btype, variant=None, **props):
    b = site_blocks.block_defaults(btype)
    if variant and site_blocks.valid_variant(btype, variant):
        b['variant'] = variant
    b['props'].update({k: v for k, v in props.items() if v is not None})
    return b


def _pick(rng, btype):
    """A random valid variant for a block type."""
    return rng.choice(site_blocks.REGISTRY[btype]['variants'])


def _theme(rng):
    """Pick a preset, then nudge a token or two so even two schools that land on
    the same preset still differ."""
    preset = rng.choice(list(PRESETS.keys()))
    theme = {'preset': preset}
    # Occasionally override the corner rounding and button style for extra variety.
    if rng.random() < 0.5:
        theme['radius'] = rng.choice(['6px', '10px', '14px', '18px'])
    if rng.random() < 0.4:
        theme['button'] = rng.choice(['solid', 'gradient', 'outline'])
    return theme


def _home(rng, brand):
    name = brand.get('name') or 'Our School'
    motto = brand.get('motto') or 'Nurturing character, curiosity and excellence.'
    blocks = [_block('nav', _pick(rng, 'nav'))]
    # Hero — only the imageless variants so it looks finished with no uploads yet.
    hero_v = rng.choice(['center', 'gradient'])
    blocks.append(_block('hero', hero_v, eyebrow='Welcome to', heading=name, subheading=motto))

    # A sensible skeleton with randomised variants; optional sections toggled by seed.
    blocks.append(_block('about', _pick(rng, 'about'),
                         body=f'{name} is a place where every child is known, challenged and '
                              'supported. Our community brings together caring teachers, engaged '
                              'families and a rich curriculum to help each student thrive.'))
    if rng.random() < 0.6:
        blocks.append(_block('welcome', _pick(rng, 'welcome'),
                             message=f'On behalf of everyone at {name}, welcome. We are proud of '
                                     'our students and delighted you are considering joining our family.'))
    blocks.append(_block('values', _pick(rng, 'values')))
    # Programmes and features in a seed-decided order.
    core = [('programmes', _pick(rng, 'programmes')), ('features', _pick(rng, 'features'))]
    rng.shuffle(core)
    for t, v in core:
        blocks.append(_block(t, v))
    blocks.append(_block('stats', _pick(rng, 'stats')))
    if rng.random() < 0.5:
        blocks.append(_block('events', _pick(rng, 'events')))
    if rng.random() < 0.6:
        blocks.append(_block('testimonials', _pick(rng, 'testimonials')))
    blocks.append(_block('cta', _pick(rng, 'cta'),
                         heading=f'Join the {name} family',
                         subheading='Applications are open — start yours in minutes.'))
    blocks.append(_block('contact', _pick(rng, 'contact')))
    blocks.append(_block('footer', _pick(rng, 'footer'), tagline=motto))
    return blocks


def _inner_page(rng, brand, title, body_blocks):
    """nav + a titled hero + the page's own sections + footer."""
    blocks = [_block('nav', _pick(rng, 'nav')),
              _block('hero', 'center', eyebrow='', heading=title, subheading='',
                     primary_label='', secondary_label='')]
    blocks.extend(body_blocks)
    blocks.append(_block('footer', _pick(rng, 'footer'),
                         tagline=(brand.get('motto') or '')))
    return blocks


def _pages(rng, brand):
    name = brand.get('name') or 'Our School'
    about = _inner_page(rng, brand, 'About Us', [
        _block('about', _pick(rng, 'about'),
               body=f'Learn about the story, people and philosophy behind {name}.'),
        _block('welcome', _pick(rng, 'welcome')),
        _block('values', _pick(rng, 'values')),
    ])
    academics = _inner_page(rng, brand, 'Academics', [
        _block('programmes', _pick(rng, 'programmes')),
        _block('features', _pick(rng, 'features')),
    ])
    admissions = _inner_page(rng, brand, 'Admissions', [
        _block('cta', _pick(rng, 'cta'),
               heading='Ready to apply?',
               subheading=f'We would love to welcome your child to {name}.'),
        _block('contact', _pick(rng, 'contact')),
    ])
    contact = _inner_page(rng, brand, 'Contact Us', [
        _block('contact', _pick(rng, 'contact')),
    ])
    return [('about', 'About Us', about), ('academics', 'Academics', academics),
            ('admissions', 'Admissions', admissions), ('contact', 'Contact Us', contact)]


def _ai_polish(home_blocks, brand):
    """Best-effort: let the AI assistant improve a few key sections' copy. Never
    raises and is skipped entirely when the assistant isn't configured."""
    from utils import site_ai
    if not site_ai.is_available():
        return
    for b in home_blocks:
        if b['type'] not in ('hero', 'about', 'cta'):
            continue
        fields = site_ai.copy_fields(b.get('props'))
        if not fields:
            continue
        try:
            spec = site_blocks.REGISTRY.get(b['type']) or {}
            out = site_ai.suggest_block_copy(spec.get('label', b['type']), fields,
                                             b['props'], branding=brand)
            if out:
                b['props'].update(out)
        except Exception:
            continue


def generate(*, salt='', use_ai=False):
    """(Re)build the whole site. Replaces existing pages with a fresh, seeded
    design and updates the theme + SEO. Returns the number of pages created."""
    rng, name = _rng(salt)
    brand = _branding()

    settings = SiteSettings.get()
    settings.theme = _theme(rng)
    settings.seo_title = (f'{name} — Excellence in education')[:70]
    settings.seo_description = (brand.get('motto')
                                or f'Welcome to {name}. Discover our programmes and apply online.')[:180]

    home_blocks = _home(rng, brand)
    if use_ai:
        _ai_polish(home_blocks, brand)

    # Replace any existing pages with the freshly generated set.
    SitePage.query.delete()
    db.session.add(SitePage(slug=SitePage.HOME_SLUG, title='Home', blocks=home_blocks,
                            show_in_nav=True, nav_order=0))
    order = 1
    for slug, title, blocks in _pages(rng, brand):
        db.session.add(SitePage(slug=slug, title=title, blocks=blocks,
                                show_in_nav=True, nav_order=order))
        order += 1
    db.session.commit()
    return order      # 1 home + (order-1) inner pages == total pages
