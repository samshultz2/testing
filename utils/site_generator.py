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


# Curated, designer-composed layouts. Each section is (block type, variant, image
# slot) — image slot is None or one of hero/about/principal/cta/gallery/logos,
# telling the builder which prop to fill with imagery. ``topbar`` is the contact
# bar shown above the nav.
RECIPES = [
    {   # Editorial — serif, institutional, photo-led
        'name': 'editorial', 'themes': ['royal', 'forest', 'emerald', 'graphite'],
        'topbar': 'dark', 'hero': 'slider',
        'sections': [
            ('about', 'split-image', 'about'), ('stats', 'bar', None),
            ('programmes', 'cards', None), ('welcome', 'portrait-left', 'principal'),
            ('features', 'grid', None), ('gallery', 'showcase', 'gallery'),
            ('staff', 'grid', 'staff'), ('testimonials', 'cards', None),
            ('faq', 'two-col', None), ('logos', 'strip', 'logos'),
            ('cta', 'image', 'cta'), ('contact', 'split', None)],
    },
    {   # Modern — bold, sans-serif, energetic
        'name': 'modern', 'themes': ['midnight', 'plum', 'slate'],
        'topbar': 'accent', 'hero': 'slider',
        'sections': [
            ('features', 'grid', None), ('about', 'split-image', 'about'),
            ('stats', 'bar', None), ('programmes', 'grid', None),
            ('gallery', 'grid', 'gallery'), ('welcome', 'portrait-right', 'principal'),
            ('staff', 'cards', 'staff'), ('testimonials', 'cards', None),
            ('logos', 'strip', 'logos'), ('cta', 'band', None), ('contact', 'cards', None)],
    },
    {   # Warm — friendly, community-focused
        'name': 'warm', 'themes': ['coral', 'plum', 'forest'],
        'topbar': 'accent', 'hero': 'image-bg',
        'sections': [
            ('about', 'split-image', 'about'), ('values', 'three-cards', None),
            ('programmes', 'cards', None), ('gallery', 'masonry', 'gallery'),
            ('stats', 'cards', None), ('welcome', 'portrait-left', 'principal'),
            ('staff', 'grid', 'staff'), ('testimonials', 'cards', None),
            ('faq', 'accordion', None), ('cta', 'image', 'cta'), ('contact', 'split', None)],
    },
    {   # Refined — minimal, calm, lots of whitespace
        'name': 'refined', 'themes': ['slate', 'graphite', 'royal'],
        'topbar': 'light', 'hero': 'split',
        'sections': [
            ('stats', 'bar', None), ('about', 'split-image', 'about'),
            ('programmes', 'grid', None), ('features', 'alternating', None),
            ('gallery', 'grid', 'gallery'), ('staff', 'grid', 'staff'),
            ('welcome', 'portrait-right', 'principal'), ('logos', 'boxed', 'logos'),
            ('cta', 'boxed', None), ('contact', 'cards', None)],
    },
]


def _rng(salt=''):
    from models import SchoolSettings
    name = (SchoolSettings.get('school_name', '') or 'School')
    seed = int(hashlib.sha256(f'{name}|{salt}'.encode('utf-8')).hexdigest(), 16)
    return random.Random(seed), name


def _branding():
    from utils.site_data import public_branding
    return public_branding()


class _ImageSource:
    """Serves imagery for the generated site, preferring the school's own uploaded
    photos (their media library) and falling back to seeded stock photography when
    the library is empty — so a school that has added photos sees *its* photos."""

    def __init__(self, key):
        self.key = key
        self._own = self._own_urls()
        self._i = 0

    @staticmethod
    def _own_urls():
        from models import SiteMedia
        urls = []
        for m in SiteMedia.query.order_by(SiteMedia.id.asc()).all():
            try:
                urls.append(m.url)
            except Exception:
                urls.append(f'/site/media/{m.id}')
        return urls

    def has_own(self):
        return bool(self._own)

    def _take(self):
        u = self._own[self._i % len(self._own)]
        self._i += 1
        return u

    def one(self, slot, w, h):
        return self._take() if self._own else site_stock.pick(self.key, slot, w, h)

    def many(self, n, w, h):
        if self._own:
            return [self._own[i % len(self._own)] for i in range(n)]
        return site_stock.gallery(self.key, n, w, h)


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


def _fill_image(block, slot, src):
    """Drop imagery (the school's own, else stock) into a section per its slot."""
    if slot == 'about':
        block['props']['image'] = src.one('about', 1200, 900)
    elif slot == 'principal':
        block['props']['image'] = src.one('principal', 800, 900)
    elif slot == 'cta':
        block['props']['bg_image'] = src.one('cta', 1600, 800)
    elif slot == 'gallery':
        block['props']['images'] = src.many(6, 800, 600)
    elif slot == 'logos':
        block['props']['logos'] = src.many(5, 220, 120)
    elif slot == 'staff':
        for m in block['props'].get('items') or []:
            m['image'] = src.one('staff-' + (m.get('role') or ''), 600, 700)


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


def _nav_header(rng, recipe, name):
    """The topbar (contact/social) + sticky nav that opens every page."""
    return [_block('topbar', recipe.get('topbar', 'dark'),
                   message=f'Welcome to {name} · Admissions open'),
            _block('nav', rng.choice(['classic', 'minimal', 'centered']))]


def _home(rng, brand, recipe, src):
    name = brand.get('name') or 'Our School'
    motto = brand.get('motto') or 'Nurturing character, curiosity and excellence.'
    blocks = _nav_header(rng, recipe, name)

    hero = _block('hero', recipe['hero'], eyebrow='Welcome to', heading=name, subheading=motto)
    if recipe['hero'] == 'slider':
        hero['props']['slides'] = src.many(4, 1600, 900)
    elif recipe['hero'] == 'image-bg':
        hero['props']['bg_image'] = src.one('hero', 1600, 900)
    elif recipe['hero'] in ('split', 'image-right'):
        hero['props']['image'] = src.one('hero', 1100, 850)
    blocks.append(hero)

    for btype, variant, slot in recipe['sections']:
        b = _block(btype, variant)
        _copy(b, name, motto)
        if slot:
            _fill_image(b, slot, src)
        blocks.append(b)

    blocks.append(_block('footer', rng.choice(['rich', 'simple']), tagline=motto))
    return blocks


def _inner_page(rng, recipe, brand, name, title, body_blocks):
    blocks = _nav_header(rng, recipe, name)
    blocks.append(_block('hero', 'center', eyebrow='', heading=title, subheading='',
                         primary_label='', secondary_label=''))
    blocks.extend(body_blocks)
    blocks.append(_block('footer', rng.choice(['rich', 'simple']),
                         tagline=(brand.get('motto') or '')))
    return blocks


def _pages(rng, recipe, brand, src):
    name = brand.get('name') or 'Our School'

    def about_block():
        b = _block('about', 'split-image'); _copy(b, name, ''); _fill_image(b, 'about', src)
        return b

    principal = _block('welcome', 'portrait-left'); _copy(principal, name, '')
    _fill_image(principal, 'principal', src)
    gal = _block('gallery', 'showcase'); _fill_image(gal, 'gallery', src)
    cta_img = _block('cta', 'image', heading='Ready to apply?',
                     subheading=f'We would love to welcome your child to {name}.')
    _fill_image(cta_img, 'cta', src)

    about = _inner_page(rng, recipe, brand, name, 'About Us', [
        about_block(), principal, _block('values', 'three-cards')])
    academics = _inner_page(rng, recipe, brand, name, 'Academics', [
        _block('programmes', 'cards'), _block('features', 'grid'), gal])
    admissions = _inner_page(rng, recipe, brand, name, 'Admissions', [
        cta_img, _block('faq', 'accordion'), _block('contact', 'split')])
    assignments = _inner_page(rng, recipe, brand, name, 'Holiday Assignments', [
        _block('assignments', 'by-class')])
    contact = _inner_page(rng, recipe, brand, name, 'Contact Us', [_block('contact', 'split')])
    return [('about', 'About Us', about), ('academics', 'Academics', academics),
            ('admissions', 'Admissions', admissions),
            ('holiday-assignments', 'Holiday Assignments', assignments),
            ('contact', 'Contact Us', contact)]


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
    src = _ImageSource(key)                    # school's own photos, else seeded stock

    settings = SiteSettings.get()
    settings.theme = _theme(rng, recipe)
    settings.seo_title = (f'{name} — Excellence in education')[:70]
    settings.seo_description = (brand.get('motto')
                                or f'Welcome to {name}. Discover our programmes and apply online.')[:180]

    home_blocks = _home(rng, brand, recipe, src)
    if use_ai:
        _ai_polish(home_blocks, brand)

    SitePage.query.delete()
    db.session.add(SitePage(slug=SitePage.HOME_SLUG, title='Home', blocks=home_blocks,
                            show_in_nav=True, nav_order=0))
    order = 1
    for slug, title, blocks in _pages(rng, recipe, brand, src):
        db.session.add(SitePage(slug=slug, title=title, blocks=blocks,
                                show_in_nav=True, nav_order=order))
        order += 1
    db.session.commit()
    return order
