"""Editor model for the Website Builder app.

Turns the block registry into something a person can edit without knowing
JSON: every prop gets a field kind (text, long text, link, image, photo list,
bullet list or a list of cards) and a plain-English label, and edits coming
back from the app are checked against the registry before they're stored.
"""
from utils import site_blocks

# Icons and one-line descriptions for the "Add a section" picker and outline.
BLOCK_META = {
    'topbar': ('fa-bullhorn', 'A slim strip with a message and social links'),
    'nav': ('fa-bars', 'Your logo, menu and an Apply button'),
    'hero': ('fa-panorama', 'The big welcome banner at the top'),
    'about': ('fa-school', 'Your school’s story with key points'),
    'welcome': ('fa-user-tie', 'A message from the principal'),
    'values': ('fa-compass', 'Vision, mission and values'),
    'stats': ('fa-chart-simple', 'Live numbers from your school'),
    'programmes': ('fa-book-open', 'The levels or programmes you offer'),
    'features': ('fa-star', 'Reasons parents choose you'),
    'events': ('fa-calendar-days', 'Upcoming events from your calendar'),
    'news': ('fa-bolt', 'Short highlights you type here'),
    'blog': ('fa-newspaper', 'Your latest news posts'),
    'gallery': ('fa-images', 'A grid of photos'),
    'staff': ('fa-people-group', 'Leadership with photos'),
    'fees': ('fa-money-bill-wave', 'Your fee schedule'),
    'assignments': ('fa-file-arrow-down', 'Holiday assignments to download'),
    'testimonials': ('fa-quote-left', 'Kind words from parents'),
    'cta': ('fa-hand-pointer', 'A bold invitation to apply'),
    'logos': ('fa-award', 'Accreditation and partner logos'),
    'faq': ('fa-circle-question', 'Common questions and answers'),
    'contact': ('fa-location-dot', 'Address, phone, email and map'),
    'footer': ('fa-grip-lines', 'The bottom of every page'),
}

DATA_NOTE = {
    'branding': 'Your school name, logo and contact details come from Settings automatically.',
    'stats': 'The numbers update automatically from your school records.',
    'events': 'Events come from your school calendar automatically.',
    'posts': 'Shows the posts you write under News.',
    'assignments': 'Shows the files you upload under Assignments.',
}

LABELS = {
    'eyebrow': 'Small line above the heading', 'heading': 'Heading', 'subheading': 'Text under the heading',
    'primary_label': 'Main button text', 'primary_href': 'Main button link',
    'secondary_label': 'Second button text', 'secondary_href': 'Second button link',
    'image': 'Picture', 'bg_image': 'Background picture', 'slides': 'Slideshow photos',
    'body': 'Text', 'points': 'Key points', 'name': 'Name', 'role': 'Role', 'message': 'Message',
    'items': 'Items', 'established_label': 'Label for the founding year', 'empty': 'Text when there is nothing to show',
    'intro': 'Introduction', 'images': 'Photos', 'note': 'Note', 'button_label': 'Button text',
    'button_href': 'Button link', 'logos': 'Logos', 'map_embed': 'Google Maps embed link',
    'tagline': 'Tagline', 'cta_label': 'Button text', 'cta_href': 'Button link',
    'facebook': 'Facebook link', 'instagram': 'Instagram link', 'twitter': 'X (Twitter) link',
    'youtube': 'YouTube link', 'linkedin': 'LinkedIn link',
    'title': 'Title', 'icon': 'Icon', 'date': 'Date', 'href': 'Link', 'bio': 'Short bio',
    'level': 'Class level', 'amount': 'Amount', 'quote': 'What they said', 'q': 'Question', 'a': 'Answer',
}

# What each list of cards is called, so buttons read "Add question" not "Add item".
ITEM_NOUN = {
    'values': 'statement', 'programmes': 'programme', 'features': 'reason', 'news': 'highlight',
    'staff': 'person', 'fees': 'fee', 'testimonials': 'testimonial', 'faq': 'question',
}

_LONG = {'body', 'message', 'subheading', 'intro', 'note', 'empty', 'tagline', 'bio', 'quote', 'a', 'map_embed'}
_LINK_KEYS = {'href', 'facebook', 'instagram', 'twitter', 'youtube', 'linkedin'}
MAX_TEXT = 5000


def label(key):
    return LABELS.get(key) or key.replace('_', ' ').capitalize()


def _kind(key, default, value):
    if key.endswith('_href') or key in _LINK_KEYS:
        return 'link'
    if key in ('image', 'bg_image'):
        return 'image'
    if key == 'icon':
        return 'icon'
    if key in _LONG:
        return 'long'
    if isinstance(value, str) and len(value) > 80:
        return 'long'
    return 'text'


def fields(btype, props):
    """Field descriptors for every editable prop on a block, in registry order."""
    spec = site_blocks.REGISTRY.get(btype) or {}
    defaults = spec.get('props') or {}
    imgs = set(spec.get('images') or [])
    ilist = spec.get('image_list')
    out = []
    for key in list(defaults) + [k for k in (props or {}) if k not in defaults]:
        dflt = defaults.get(key)
        val = (props or {}).get(key, dflt)
        f = {'key': key, 'label': label(key)}
        if key in imgs:
            f['kind'] = 'image'
        elif key == ilist:
            f['kind'] = 'images'
        elif isinstance(dflt if dflt is not None else val, list):
            sample = (dflt or []) + (val if isinstance(val, list) else [])
            if any(isinstance(x, dict) for x in sample):
                keys = []
                for x in sample:
                    if isinstance(x, dict):
                        keys += [k for k in x if k not in keys]
                f['kind'] = 'items'
                f['noun'] = ITEM_NOUN.get(btype, 'item')
                f['item_fields'] = [{'key': k, 'label': label(k), 'kind': _kind(k, '', '')} for k in keys]
            else:
                f['kind'] = 'strings'
        elif isinstance(val, (dict, list)):
            continue
        else:
            f['kind'] = _kind(key, dflt, val)
        out.append(f)
    return out


def merged_props(block):
    """The block's props with any newer registry fields filled in, so a section
    created before a field existed can still edit it."""
    spec = site_blocks.REGISTRY.get(block.get('type')) or {}
    import copy
    props = copy.deepcopy(spec.get('props') or {})
    props.update(block.get('props') or {})
    return props


def variant_label(v):
    return (v or '').replace('-', ' ').capitalize()


def serialize_block(block, idx, ai_available=False):
    from utils import site_ai
    btype = block.get('type')
    spec = site_blocks.REGISTRY.get(btype) or {}
    icon, desc = BLOCK_META.get(btype, ('fa-cube', ''))
    props = merged_props(block)
    flds = fields(btype, props)
    return {
        'idx': idx, 'type': btype, 'label': spec.get('label', btype), 'icon': icon, 'desc': desc,
        'variant': block.get('variant'),
        'variants': [{'value': v, 'label': variant_label(v)} for v in spec.get('variants', [])],
        'image_variants': spec.get('image_variants', {}),
        'enabled': block.get('enabled', True),
        'props': props, 'fields': flds,
        'note': DATA_NOTE.get(spec.get('data')) if spec.get('data') else None,
        'ai': bool(ai_available and site_ai.copy_fields(props)),
        'summary': _summary(props),
    }


def _summary(props):
    for k in ('heading', 'message', 'title', 'tagline', 'cta_label'):
        v = props.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()[:80]
    return ''


def catalogue():
    return [{'type': c['type'], 'label': c['label'], 'icon': BLOCK_META.get(c['type'], ('fa-cube', ''))[0],
             'desc': BLOCK_META.get(c['type'], ('', ''))[1]} for c in site_blocks.catalogue()]


def clean_props(btype, current, incoming):
    """Validate edited props from the app. Only known keys are kept, each value
    must keep the shape of the registry default (text stays text, lists stay
    lists of text or of cards). Raises ValueError with a friendly message."""
    if not isinstance(incoming, dict):
        raise ValueError('Nothing to save.')
    spec = site_blocks.REGISTRY.get(btype) or {}
    allowed = merged_props({'type': btype, 'props': current})
    out = dict(allowed)
    for key, val in incoming.items():
        if key not in allowed:
            continue
        shape = allowed[key]
        if isinstance(shape, str) or shape is None:
            if val is None:
                val = ''
            if not isinstance(val, str):
                raise ValueError(f'“{label(key)}” must be text.')
            out[key] = val[:MAX_TEXT]
        elif isinstance(shape, list):
            if not isinstance(val, list):
                raise ValueError(f'“{label(key)}” must be a list.')
            clean = []
            for x in val[:60]:
                if isinstance(x, str):
                    clean.append(x[:MAX_TEXT])
                elif isinstance(x, dict):
                    clean.append({str(k)[:40]: ('' if v is None else str(v))[:MAX_TEXT]
                                  for k, v in x.items() if isinstance(v, (str, int, float)) or v is None})
            if key == spec.get('image_list'):
                clean = [x for x in clean if isinstance(x, str) and x.strip()]
            out[key] = clean
    return out
