// Client-side section navigation (no full reload). Each section's page routes
// return their JSON payload when asked via fetch (see utils/spa.render_or_json),
// so we can navigate / filter / refresh in place and keep the URL in sync.
import { useState, useEffect, useCallback, createContext, useContext } from 'react';

// Section navigation made available to any screen without prop-drilling.
export const NavCtx = createContext({ go: (u) => { window.location = u; }, refresh: () => {} });
export const useNav = () => useContext(NavCtx);

// Global soft-navigation coordination: the app-wide `spa-nav.js` layer can swap
// the whole page (e.g. when the sidebar menu is used to jump to another section).
// When it does, any section mounted into the now-detached DOM must stop reacting
// to history events. Each loaded bundle keeps its own generation counter; a swap
// bumps it, so handlers captured before the swap become no-ops.
let _navGen = 0;
if (typeof window !== 'undefined') {
  window.addEventListener('spa:swapping', () => { _navGen += 1; });
}

// Drive the shared top progress bar during in-section navigation so the user
// always gets a loading cue (the bar lives in base.html).
function _progress(on) {
  if (typeof document === 'undefined') return;
  const bar = document.getElementById('navProgress');
  if (!bar) return;
  if (on) { bar.style.opacity = '1'; bar.style.width = '65%'; }
  else { bar.style.width = '100%'; setTimeout(() => { bar.style.opacity = '0'; bar.style.width = '0'; }, 200); }
}

// Build a section URL with query params and navigate to it (no reload).
export function navParams(go, url, params) {
  const qs = new URLSearchParams(params).toString();
  return go(qs ? url + '?' + qs : url);
}

export async function fetchPage(url) {
  const res = await fetch(url, {
    credentials: 'same-origin',
    headers: { 'X-Requested-With': 'fetch', Accept: 'application/json' },
  });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}

// Holds the current page payload; `go(url)` swaps it in place + pushes history,
// `refresh()` re-fetches the current URL (e.g. after a mutation). Falls back to a
// real navigation if the target isn't a JSON section page.
export function useSection(initial) {
  const [data, setData] = useState(initial);
  const [loading, setLoading] = useState(false);

  const go = useCallback(async (url, opts = {}) => {
    setLoading(true);
    _progress(true);
    try {
      const payload = await fetchPage(url);
      setData(payload);
      window.history[opts.replace ? 'replaceState' : 'pushState']({ spa: 1 }, '', url);
      if (!opts.keepScroll) window.scrollTo(0, 0);
    } catch (e) {
      window.location = url;   // cross-section / non-JSON target
    } finally {
      setLoading(false);
      _progress(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    try { setData(await fetchPage(window.location.href)); } catch (_) { /* keep */ }
  }, []);

  useEffect(() => {
    const myGen = _navGen;   // if a global swap happens later, this instance is stale
    const onPop = () => {
      if (_navGen !== myGen) return;   // the page was swapped out by the global nav
      fetchPage(window.location.href).then(setData).catch(() => {});
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  return { data, loading, go, refresh, setData };
}
