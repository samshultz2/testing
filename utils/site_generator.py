"""One-click website generation for the Website Builder.

Builds a complete, professionally-composed multi-page site — theme, pages,
sections, imagery and copy — in a single step, so a school admin who can't
design gets a finished, good-looking site to start from.

Quality comes from curated *design recipes*: hand-composed combinations of
section variants (the kind a designer would choose), not random ones. Uniqueness
comes from seeding every choice — recipe, theme, imagery and copy — with the
school's own identity, so two schools get genuinely different sites while the
same school is deterministic. Sites are image-forward: each recipe places stock
photography (via ``utils.site_stock``) into hero, about, principal, gallery and
CTA slots, and every image can be swapped for the school's own upload later.

Because it produces ordinary ``SitePage``/``SiteSettings`` rows, everything it
makes is fully editable in the normal editor afterwards.
"""
import hashlib
import random

from models import db, SiteSettings, SitePage
from utils import site_blocks, site_stock
from utils.site_themes import PRESETS


# Curated, designer-composed layouts. Each entry is (block type, variant, image
# slot) — image slot is None or one of hero/about/principal/cta/gallery, which
# tells the builder to drop stock photography into the right prop.
RECIPES = [
    {   # Editorial — serif, institutional, photo-led
        'name': 'editorial', 'themes': ['royal', 'forest', 'emerald', 'graphite'],
        'hero': 'image-bg',
        'sections': [
            ('about', 'split-image', 'about'), ('stats', 'bar', None),
            ('programmes', 'cards', None), ('welcome', 'portrait-left', 'principal'),
            ('features', 'grid', None), ('gallery', 'showcase', 'gallery'),
            ('testimonials', 'cards', None), ('cta', 'image', 'cta'),
            ('contact', 'split', None)],
    },
    {   # Modern — bold, sans-serif, energetic
        'name': 'modern', 'themes': ['midnight', 'plum', 'slate'],
        'hero': 'image-bg',
        'sections': [
            ('features', 'grid', None), ('about', 'split-image', 'about'),
            ('stats', 'bar', None), ('programmes', 'grid', None),
            ('gallery', 'grid', 'gallery'), ('welcome', 'portrait-right', 'principal'),
            ('testimonials', 'cards', None), ('cta', 'band', None),
            ('contact', 'cards', None)],
    },
    {   # Warm — friendly, community-focused
        'name': 'warm', 'themes': ['coral', 'plum', 'forest'],
        'hero': 'image-bg',
        'sections': [
            ('about', 'split-image', 'about'), ('values', 'three-cards', None),
            ('programmes', 'cards', None), ('gallery', 'masonry', 'gallery'),
            ('stats', 'cards', None), ('welcome', 'portrait-left', 'principal'),
            ('testimonials', 'cards', None), ('cta', 'image', 'cta'),
            ('contact', 'split', None)],
    },
    {   # Refined — minimal, calm, lots of whitespace
        'name': 'refined', 'themes': ['slate', 'graphite', 'royal'],
        'hero': 'split',
        'sections': [
            ('stats', 'bar', None), ('about', 'split-image', 'about'),
            ('programmes', 'grid', None), ('features', 'alternating', None),
            ('gallery', 'grid', 'gallery'), ('welcome', 'portrait-right', 'principal'),
            ('cta', 'boxed', None), ('contact', 'cards', None)],
    },
]


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


def _theme(rng, recipe):
    """Preset from the recipe's family, with a small token nudge so even two
    schools that land on the same recipe+preset still differ."""
    preset = rng.choice(recipe['themes'])
    theme = {'preset': preset}
    if rng.random() < 0.5:
        theme['radius'] = rng.choice(['6px', '10px', '14px', '18px'])
    if rng.random() < 0.4:
        theme['button'] = rng.choice(['solid', 'gradient', 'outline'])
    return theme


def _fill_image(block, slot, key):
    """Drop stock photography into a section according to its recipe slot."""
    if slot == 'about':
        block['props']['image'] = site_stock.pick(key, 'about', 1200, 900)
    elif slot == 'principal':
        block['props']['image'] = site_stock.pick(key, 'principal', 800, 900)
    elif slot == 'cta':
        block['props']['bg_image'] = site_stock.pick(key, 'cta', 1600, 800)
    elif slot == 'gallery':
        block['props']['images'] = site_stock.gallery(key, 6, 800, 600)


def _copy(block, name, motto):
    """Brand a section's copy from the school's name/motto so it reads as theirs."""
    t = block['type']
    if t == 'about':
        block['props']['body'] = (
            f'{name} is a place where every child is known, challenged and supported. '
            'Our community brings together caring teachers, engaged families and a '
            'rich curriculum so each student can discover their strengths and thrive.')
    elif t == 'welcome':
        block['props']['message'] = (
            f'On behalf of everyone at {name}, welcome. We are proud of our students '
            'and the warm, ambitious community we have built — and we would be '
            'delighted for your family to be part of it.')
    elif t == 'cta':
        block['props']['heading'] = f'Join the {name} family'
        block['props']['subheading'] = 'Admissions are open — start your application in minutes.'


def _home(rng, brand, recipe, key):
    name = brand.get('name') or 'Our School'
    motto = brand.get('motto') or 'Nurturing character, curiosity and excellence.'
    blocks = [_block('nav', rng.choice(['classic', 'minimal', 'centered']))]

    hero = _block('hero', recipe['hero'], eyebrow='Welcome to', heading=name, subheading=motto)
    if recipe['hero'] == 'image-bg':
        hero['props']['bg_image'] = site_stock.pick(key, 'hero', 1600, 900)
    elif recipe['hero'] in ('split', 'image-right'):
        hero['props']['image'] = site_stock.pick(key, 'hero', 1100, 850)
    blocks.append(hero)

    for btype, variant, slot in recipe['sections']:
        b = _block(btype, variant)
        _copy(b, name, motto)
        if slot:
            _fill_image(b, slot, key)
        blocks.append(b)

    blocks.append(_block('footer', rng.choice(['rich', 'simple']), tagline=motto))
    return blocks


def _inner_page(rng, brand, key, title, body_blocks):
    blocks = [_block('nav', rng.choice(['classic', 'minimal', 'centered'])),
              _block('hero', 'center', eyebrow='', heading=title, subheading='',
                     primary_label='', secondary_label='')]
    blocks.extend(body_blocks)
    blocks.append(_block('footer', rng.choice(['rich', 'simple']),
                         tagline=(brand.get('motto') or '')))
    return blocks


def _about_block(key, variant='split-image'):
    b = _block('about', variant)
    _fill_image(b, 'about', key)
    return b


def _pages(rng, brand, key):
    name = brand.get('name') or 'Our School'
    principal = _block('welcome', 'portrait-left'); _fill_image(principal, 'principal', key)
    gal = _block('gallery', 'showcase'); _fill_image(gal, 'gallery', key)
    cta_img = _block('cta', 'image', heading='Ready to apply?',
                     subheading=f'We would love to welcome your child to {name}.')
    _fill_image(cta_img, 'cta', key)

    about = _inner_page(rng, brand, key, 'About Us', [
        _about_block(key), principal, _block('values', 'three-cards')])
    academics = _inner_page(rng, brand, key, 'Academics', [
        _block('programmes', 'cards'), _block('features', 'grid'), gal])
    admissions = _inner_page(rng, brand, key, 'Admissions', [
        cta_img, _block('contact', 'split')])
    contact = _inner_page(rng, brand, key, 'Contact Us', [_block('contact', 'split')])
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
    """(Re)build the whole site with a fresh, seeded, image-rich design. Replaces
    existing pages and updates the theme + SEO. Returns the page count."""
    rng, name = _rng(salt)
    brand = _branding()
    key = f'{name}|{salt}'                    # image seed: unique per school + variation
    recipe = rng.choice(RECIPES)

    settings = SiteSettings.get()
    settings.theme = _theme(rng, recipe)
    settings.seo_title = (f'{name} — Excellence in education')[:70]
    settings.seo_description = (brand.get('motto')
                                or f'Welcome to {name}. Discover our programmes and apply online.')[:180]

    home_blocks = _home(rng, brand, recipe, key)
    if use_ai:
        _ai_polish(home_blocks, brand)

    SitePage.query.delete()
    db.session.add(SitePage(slug=SitePage.HOME_SLUG, title='Home', blocks=home_blocks,
                            show_in_nav=True, nav_order=0))
    order = 1
    for slug, title, blocks in _pages(rng, brand, key):
        db.session.add(SitePage(slug=slug, title=title, blocks=blocks,
                                show_in_nav=True, nav_order=order))
        order += 1
    db.session.commit()
    return order
