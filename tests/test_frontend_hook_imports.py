"""Guard: every React hook a SPA uses must be imported from 'react'.

React is externalised to window.React by the esbuild config, so a bare named
import that's missing does NOT fail the build — it resolves to an undefined
global and only explodes at runtime in the browser (as `useRef is not defined`
did on /sales/products). This test catches that statically for all bundles.
"""
import os
import re
import glob

# The hooks React actually exports. Custom hooks (useNav, useSection, …) are not
# in this set, so they're correctly ignored.
REACT_HOOKS = {
    'useState', 'useEffect', 'useRef', 'useMemo', 'useCallback', 'useReducer',
    'useContext', 'useLayoutEffect', 'useImperativeHandle', 'useId',
    'useTransition', 'useDeferredValue', 'useSyncExternalStore',
}

_SRC = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'src')


def _imported_hooks(source):
    """Names pulled in via `import ... from 'react'` (named + namespace alias)."""
    named = set()
    for m in re.finditer(r"import\s+(.+?)\s+from\s+['\"]react['\"]", source, re.S):
        clause = m.group(1)
        for b in re.findall(r'\{([^}]*)\}', clause):
            named.update(part.strip().split(' as ')[0].strip()
                         for part in b.split(',') if part.strip())
    return named


def test_all_spas_import_the_hooks_they_use():
    problems = []
    for path in glob.glob(os.path.join(_SRC, '**', '*.jsx'), recursive=True):
        with open(path, encoding='utf-8') as fh:
            src = fh.read()
        if "from 'react'" not in src and 'from "react"' not in src:
            continue
        imported = _imported_hooks(src)
        for hook in REACT_HOOKS:
            # bare call `useRef(` that isn't a `React.useRef(` member access
            if re.search(r'(?<![.\w])' + hook + r'\s*\(', src) and hook not in imported:
                problems.append(f'{os.path.relpath(path, _SRC)} uses {hook} without importing it')
    assert not problems, 'React hooks used without import:\n  ' + '\n  '.join(problems)
