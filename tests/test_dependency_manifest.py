"""Guard against dependency drift: every third-party package imported by the
deployed app code must be acknowledged in requirements.txt.

This is the test that would have caught the missing `beautifulsoup4` (utils/
myschool.py imports bs4 but it was never declared) before it broke a fresh
environment. A dependency counts as "acknowledged" if it appears in
requirements.txt at all — including a commented-out line, which is how the
project records intentionally-optional deps (anthropic, sentry-sdk, …).
"""
import ast
import os
import sys
import importlib.metadata as md

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The deployed application surface. Dev/ops one-offs (scripts/, migrations,
# root maintenance scripts) are intentionally excluded.
_SOURCE_DIRS = ['utils', 'models', 'routes']
_SOURCE_FILES = ['app.py', 'config.py', 'wsgi.py', 'app_production.py']

# First-party top-level import names (never third-party).
_FIRST_PARTY = {
    'utils', 'models', 'routes', 'config', 'app', 'app_production', 'wsgi',
}


def _normalize(name):
    return name.lower().replace('_', '-')


def _declared_distributions():
    """Distribution names mentioned anywhere in requirements.txt — commented
    lines included, so acknowledged-optional deps count as declared."""
    declared = set()
    path = os.path.join(_ROOT, 'requirements.txt')
    with open(path) as fh:
        for raw in fh:
            line = raw.strip().lstrip('#').strip()
            if not line:
                continue
            # Cut version specifiers, extras and inline comments.
            for sep in (' ', '#', '=', '>', '<', '!', '~', '['):
                idx = line.find(sep)
                if idx != -1:
                    line = line[:idx]
            if line:
                declared.add(_normalize(line))
    return declared


def _iter_source_files():
    for d in _SOURCE_DIRS:
        for root, _dirs, files in os.walk(os.path.join(_ROOT, d)):
            if '__pycache__' in root:
                continue
            for f in files:
                if f.endswith('.py'):
                    yield os.path.join(root, f)
    for f in _SOURCE_FILES:
        p = os.path.join(_ROOT, f)
        if os.path.exists(p):
            yield p


def _import_roots(path):
    """Top-level module names imported by a file (absolute imports only)."""
    with open(path) as fh:
        try:
            tree = ast.parse(fh.read(), filename=path)
        except SyntaxError:
            return set()
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                roots.add(a.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:      # skip relative imports
                roots.add(node.module.split('.')[0])
    return roots


def test_all_third_party_imports_are_declared():
    stdlib = set(getattr(sys, 'stdlib_module_names', set()))
    pkg_to_dist = md.packages_distributions()
    declared = _declared_distributions()

    offenders = {}          # import root -> distribution missing from requirements
    for path in _iter_source_files():
        for root in _import_roots(path):
            if root in _FIRST_PARTY or root in stdlib:
                continue
            dists = pkg_to_dist.get(root)
            if not dists:
                # Not an installed distribution we can map (namespace pkg, local
                # shim, or a lazily-optional import) — don't guess.
                continue
            if not any(_normalize(d) in declared for d in dists):
                rel = os.path.relpath(path, _ROOT)
                offenders.setdefault(dists[0], (root, rel))

    assert not offenders, (
        'Third-party packages imported by app code but not acknowledged in '
        'requirements.txt (add them, or a commented line if optional): '
        + ', '.join(f'{dist} (import {root}, e.g. {where})'
                    for dist, (root, where) in sorted(offenders.items())))
