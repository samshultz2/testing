"""Stock photography for auto-generated sites.

Schools rarely have a photo library on day one, so a generated site would look
empty without imagery. This provides real, royalty-free stock photos from the
internet, chosen deterministically from a seed so a given school always gets the
same set (and two schools get different sets). Heroes and CTAs place a dark
overlay over the photo, so the result reads as a designed section regardless of
the exact image — and every image can be swapped for the school's own upload.

Source is a public photo CDN (Picsum by default) requiring no API key; override
with WEBSITE_STOCK_IMAGE_BASE. Images load under the site's ``img-src https:``
policy.
"""
import os
import re

from config import Config


def _base():
    return (os.environ.get('WEBSITE_STOCK_IMAGE_BASE', '')
            or getattr(Config, 'WEBSITE_STOCK_IMAGE_BASE', 'https://picsum.photos')).rstrip('/')


def _slug(text):
    return re.sub(r'[^a-z0-9]+', '-', (text or 'school').lower()).strip('-') or 'school'


def photo(seed, w=1600, h=900):
    """A deterministic stock photo URL for ``seed`` at the given size."""
    return f'{_base()}/seed/{_slug(seed)}/{int(w)}/{int(h)}'


def pick(key, slot, w=1600, h=900):
    """A stable photo for one image slot of one school (e.g. hero, about, cta)."""
    return photo(f'{_slug(key)}-{slot}', w, h)


def gallery(key, n=6, w=800, h=600):
    """A set of ``n`` distinct photos for a gallery, stable for this school."""
    return [photo(f'{_slug(key)}-gallery-{i}', w, h) for i in range(max(0, n))]
