// Client-side section navigation (no full reload). Each section's page routes
// return their JSON payload when asked via fetch (see utils/spa.render_or_json),
// so we can navigate / filter / refresh in place and keep the URL in sync.
import { useState, useEffect, useCallback, useRef, createContext, useContext } from 'react';

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

// Skeleton loading overlay shown while a section page's data is being fetched.
// Driven centrally (like the progress bar) so every section gets it without per
// app wiring. A short delay avoids a flash on fast (cached) loads.
if (typeof document !== 'undefined' && !document.getElementById('skeletonStyles')) {
  const st = document.createElement('style');
  st.id = 'skeletonStyles';
  st.textContent =
    '@keyframes skShimmer{0%{background-position:-468px 0}100%{background-position:468px 0}}'
    + '#sectionSkeleton{position:absolute;inset:0;background:var(--bg,#fff);z-index:50;padding:1rem 1.25rem;overflow:hidden}'
    + '#sectionSkeleton .sk-bar{height:14px;border-radius:6px;margin:10px 0;background:rgba(135,135,135,.16);'
    + 'background-image:linear-gradient(90deg,rgba(135,135,135,.12) 0,rgba(135,135,135,.28) 40px,rgba(135,135,135,.12) 80px);'
    + 'background-size:600px 100%;animation:skShimmer 1.15s infinite linear}'
    + '#sectionSkeleton .sk-title{height:26px;width:42%;margin-bottom:20px}'
    + '#sectionSkeleton .sk-bar.short{width:55%}'
    + '#sectionSkeleton .sk-card{border:1px solid rgba(135,135,135,.18);border-radius:10px;padding:14px 16px;margin-bottom:12px}';
  document.head.appendChild(st);
}

let _skelTimer = null;
function _skeleton(on) {
  if (typeof document === 'undefined') return;
  if (on) {
    if (_skelTimer || document.getElementById('sectionSkeleton')) return;
    _skelTimer = setTimeout(() => {
      _skelTimer = null;
      const host = document.querySelector('.page-content');
      if (!host || document.getElementById('sectionSkeleton')) return;
      if (getComputedStyle(host).position === 'static') host.style.position = 'relative';
      const ov = document.createElement('div');
      ov.id = 'sectionSkeleton';
      ov.setAttribute('aria-hidden', 'true');
      ov.innerHTML = '<div class="sk-bar sk-title"></div>'
        + '<div class="sk-card"><div class="sk-bar"></div><div class="sk-bar short"></div></div>'.repeat(5);
      host.appendChild(ov);
    }, 180);
  } else {
    if (_skelTimer) { clearTimeout(_skelTimer); _skelTimer = null; }
    const ov = document.getElementById('sectionSkeleton');
    if (ov) ov.remove();
  }
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
  const [offline, setOffline] = useState(false);
  const staleRef = useRef(false);   // last fetch failed → we have stale data to refresh

  // Fetch a section payload. `silent` skips the loading UI (for background
  // reconnect refreshes); returns whether it succeeded.
  const load = useCallback(async (url, opts = {}) => {
    if (!opts.silent) { setLoading(true); _progress(true); _skeleton(true); }
    try {
      const payload = await fetchPage(url);
      setData(payload);
      staleRef.current = false;
      setOffline(false);
      if (opts.push) window.history.pushState({ spa: 1 }, '', url);
      else if (opts.replace) window.history.replaceState({ spa: 1 }, '', url);
      if (!opts.keepScroll && (opts.push || opts.replace)) window.scrollTo(0, 0);
      return true;
    } catch (e) {
      staleRef.current = true;
      setOffline(true);
      return false;
    } finally {
      if (!opts.silent) { setLoading(false); _progress(false); _skeleton(false); }
    }
  }, []);

  const go = useCallback(async (url, opts = {}) => {
    const ok = await load(url, { push: !opts.replace, replace: opts.replace, keepScroll: opts.keepScroll });
    if (!ok) window.location = url;   // cross-section / non-JSON / not cached offline
  }, [load]);

  const refresh = useCallback(() => load(window.location.href, { silent: true }), [load]);

  useEffect(() => {
    const myGen = _navGen;   // if a global swap happens later, this instance is stale
    const onPop = () => { if (_navGen === myGen) load(window.location.href); };
    // Refetch within ~10s of the connection returning: react to the 'online'
    // event, and poll as a safety net (the event is sometimes missed) but only
    // when the last fetch failed, so we don't hammer the server needlessly.
    const onOnline = () => { if (_navGen === myGen) refresh(); };
    // Going offline marks the data stale even if it loaded from cache, so the
    // reconnect refresh always runs (cached responses look identical to live).
    const onOffline = () => { staleRef.current = true; setOffline(true); };
    window.addEventListener('popstate', onPop);
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    const poll = setInterval(() => {
      if (_navGen === myGen && staleRef.current && navigator.onLine) refresh();
    }, 5000);
    return () => {
      window.removeEventListener('popstate', onPop);
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
      clearInterval(poll);
    };
  }, [load, refresh]);

  return { data, loading, offline, go, refresh, setData };
}
