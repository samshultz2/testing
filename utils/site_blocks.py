"""Block registry for the Website Builder.

A block is a component instance: ``{type, variant, enabled, props}``. This module
is the catalogue — every block type, its structurally-distinct variants, the
prop schema the editor exposes, and which (PII-safe) live data source it reads.
The HTML for each type/variant lives in ``templates/website/blocks.html`` so all
output goes through Jinja autoescaping. Adding a variant is a registry entry plus
a branch in that macro — deliberately cheap, so the library can grow toward the
full catalogue over time.
"""

# data: which utils.site_data key the block pulls live SIS content from (or None
# for fully school-authored blocks). props: the editable fields (with defaults).
REGISTRY = {
    'topbar': {
        'label': 'Top contact bar', 'data': 'branding',
        'variants': ['dark', 'accent', 'light'],
        'props': {'message': 'Admissions open for the new session',
                  'facebook': '', 'instagram': '', 'twitter': '', 'youtube': '', 'linkedin': ''},
    },
    'nav': {
        'label': 'Navigation bar', 'data': 'branding', 'nav': True,
        'variants': ['classic', 'minimal', 'centered'],
        'props': {'cta_label': 'Apply', 'cta_href': '/site/apply'},
    },
    'hero': {
        'label': 'Hero section', 'data': 'branding',
        'variants': ['center', 'split', 'gradient', 'image-right', 'image-bg', 'slider'],
        'images': ['image', 'bg_image'],
        'image_list': 'slides',          # the 'slider' variant rotates these photos
        # which variants actually render each image prop (used to auto-switch the
        # design when an admin uploads an image to a variant that would hide it)
        'image_variants': {'image': ['image-right', 'split'], 'bg_image': ['image-bg']},
        'props': {'eyebrow': 'Welcome to', 'heading': '', 'subheading':
                  'Nurturing character, curiosity and excellence.',
                  'primary_label': 'Apply for admission', 'primary_href': '/site/apply',
                  'secondary_label': 'Explore programmes', 'secondary_href': '/site/academics',
                  'image': '', 'bg_image': '', 'slides': []},
    },
    'about': {
        'label': 'About section', 'data': None,
        'variants': ['text', 'split-image', 'cards'],
        'images': ['image'],
        'image_variants': {'image': ['split-image']},
        'props': {'heading': 'About our school', 'body':
                  'Tell your school’s story here — history, philosophy and what makes it special.',
                  'image': '', 'points': ['Qualified, caring teachers', 'Safe, modern facilities',
                                          'Strong academic record']},
    },
    'welcome': {
        'label': "Principal’s welcome", 'data': None,
        'variants': ['portrait-left', 'portrait-right', 'quote'],
        'images': ['image'],
        'image_variants': {'image': ['portrait-left', 'portrait-right']},
        'props': {'heading': 'A word from our Principal', 'name': '', 'role': 'Principal',
                  'message': 'Share a warm welcome message from the head of school.', 'image': ''},
    },
    'values': {
        'label': 'Vision / Mission / Values', 'data': None,
        'variants': ['three-cards', 'split', 'stacked'],
        'props': {'heading': 'Our vision & values',
                  'items': [{'title': 'Vision', 'body': 'Your vision statement.'},
                            {'title': 'Mission', 'body': 'Your mission statement.'},
                            {'title': 'Values', 'body': 'Integrity · Excellence · Community'}]},
    },
    'stats': {
        'label': 'Statistics', 'data': 'stats',
        'variants': ['bar', 'cards'],
        'props': {'heading': 'Our school at a glance', 'established_label': 'Established'},
    },
    'programmes': {
        'label': 'Academic programmes', 'data': None,
        'variants': ['grid', 'cards', 'list'],
        'props': {'heading': 'Academic programmes',
                  'items': [{'title': 'Nursery', 'body': 'Early-years foundation.', 'icon': 'fa-child'},
                            {'title': 'Primary', 'body': 'Building strong basics.', 'icon': 'fa-book'},
                            {'title': 'Secondary', 'body': 'WAEC & JAMB preparation.', 'icon': 'fa-graduation-cap'}]},
    },
    'features': {
        'label': 'Why choose us', 'data': None,
        'variants': ['grid', 'alternating'],
        'props': {'heading': 'Why choose us',
                  'items': [{'title': 'Experienced staff', 'body': 'Dedicated, qualified teachers.', 'icon': 'fa-chalkboard-teacher'},
                            {'title': 'Modern facilities', 'body': 'Labs, library and sports.', 'icon': 'fa-flask'},
                            {'title': 'Proven results', 'body': 'Consistent exam success.', 'icon': 'fa-trophy'}]},
    },
    'events': {
        'label': 'Upcoming events', 'data': 'events',
        'variants': ['cards', 'list', 'timeline'],
        'props': {'heading': 'Upcoming events', 'empty': 'No upcoming events right now — check back soon.'},
    },
    'news': {
        'label': 'News & highlights', 'data': None,
        'variants': ['cards', 'list'],
        'props': {'heading': 'Latest news',
                  'items': [{'title': 'Share a highlight', 'date': '', 'body': 'Add school news here.', 'href': ''}]},
    },
    'gallery': {
        'label': 'Gallery', 'data': None,
        'variants': ['grid', 'masonry', 'showcase'],
        'image_list': 'images',
        'props': {'heading': 'Life at our school', 'images': []},
    },
    'staff': {
        'label': 'Staff / leadership', 'data': None,
        'variants': ['grid', 'cards'],
        'props': {'heading': 'Meet our leadership', 'intro': '',
                  'items': [
                      {'name': 'Principal’s name', 'role': 'Principal', 'image': '', 'bio': ''},
                      {'name': 'Vice Principal', 'role': 'Vice Principal (Academics)', 'image': '', 'bio': ''},
                      {'name': 'Head of Admissions', 'role': 'Admissions Officer', 'image': '', 'bio': ''}]},
    },
    'assignments': {
        'label': 'Holiday assignments', 'data': 'assignments',
        'variants': ['by-class', 'list'],
        'props': {'heading': 'Holiday assignments',
                  'intro': 'Select your class and download the assignment for the holiday.',
                  'empty': 'No assignments have been posted yet — please check back soon.'},
    },
    'testimonials': {
        'label': 'Testimonials', 'data': None,
        'variants': ['cards', 'single'],
        'props': {'heading': 'What parents say',
                  'items': [{'quote': 'A wonderful, caring school.', 'name': 'A parent', 'role': ''}]},
    },
    'cta': {
        'label': 'Call to action', 'data': None,
        'variants': ['band', 'boxed', 'split', 'image'],
        'images': ['bg_image'],
        'image_variants': {'bg_image': ['image']},
        'props': {'heading': 'Ready to join our school?', 'subheading':
                  'Applications are open for the new session.',
                  'button_label': 'Start your application', 'button_href': '/site/apply',
                  'bg_image': ''},
    },
    'logos': {
        'label': 'Accreditations / partners', 'data': None,
        'variants': ['strip', 'boxed'],
        'image_list': 'logos',
        'props': {'heading': 'Accredited & affiliated', 'logos': []},
    },
    'faq': {
        'label': 'FAQ', 'data': None,
        'variants': ['accordion', 'two-col'],
        'props': {'heading': 'Frequently asked questions',
                  'items': [
                      {'q': 'How do I apply for admission?',
                       'a': 'Click “Apply” to complete our online form. You can track your status any '
                            'time with your application number.'},
                      {'q': 'What are your school fees?',
                       'a': 'Fees vary by class level. Contact our admissions office or apply online to '
                            'receive the current fee schedule.'},
                      {'q': 'What curriculum do you follow?',
                       'a': 'We follow the Nigerian national curriculum enriched with modern teaching, '
                            'preparing students for WAEC, NECO and JAMB.'},
                      {'q': 'What are your school hours?',
                       'a': 'Classes run Monday to Friday. Get in touch for the full daily timetable and '
                            'term calendar.'}]},
    },
    'contact': {
        'label': 'Contact', 'data': 'branding',
        'variants': ['split', 'cards'],
        'props': {'heading': 'Get in touch', 'map_embed': ''},
    },
    'footer': {
        'label': 'Footer', 'data': 'branding', 'footer': True,
        'variants': ['rich', 'simple'],
        'props': {'tagline': ''},
    },
}


def block_defaults(btype):
    """A fresh block instance for ``btype`` (first variant, default props)."""
    spec = REGISTRY[btype]
    import copy
    return {'type': btype, 'variant': spec['variants'][0], 'enabled': True,
            'props': copy.deepcopy(spec['props'])}


def valid_type(btype):
    return btype in REGISTRY


def valid_variant(btype, variant):
    return btype in REGISTRY and variant in REGISTRY[btype]['variants']


def default_home_blocks():
    """A complete, good-looking starter homepage."""
    return [block_defaults(t) for t in
            ('nav', 'hero', 'about', 'values', 'stats', 'programmes',
             'features', 'events', 'cta', 'contact', 'footer')]


def default_page_blocks(slug, title):
    """A sensible starter for a named page (nav + heading hero + contact/footer)."""
    nav = block_defaults('nav')
    hero = block_defaults('hero')
    hero['variant'] = 'center'
    hero['props'].update({'eyebrow': '', 'heading': title,
                          'subheading': '', 'primary_label': '', 'secondary_label': ''})
    footer = block_defaults('footer')
    return [nav, hero, footer]


def catalogue():
    """Editor-facing catalogue: [{type, label, variants}] in registry order."""
    return [{'type': t, 'label': s['label'], 'variants': s['variants']}
            for t, s in REGISTRY.items()]


def image_props(btype):
    """Prop names on ``btype`` that hold a single image URL."""
    return set(REGISTRY.get(btype, {}).get('images', []))


def image_list_prop(btype):
    """The prop name on ``btype`` that holds a list of image URLs, or None."""
    return REGISTRY.get(btype, {}).get('image_list')


def variants_showing(btype, image_key):
    """Variants of ``btype`` that actually render ``image_key`` (empty if any)."""
    return REGISTRY.get(btype, {}).get('image_variants', {}).get(image_key, [])


def variant_for_image(btype, image_key, current_variant):
    """If ``current_variant`` wouldn't display ``image_key``, return a variant that
    does (so an uploaded image is never silently hidden); else return None."""
    shows = variants_showing(btype, image_key)
    if shows and current_variant not in shows:
        return shows[0]
    return None
