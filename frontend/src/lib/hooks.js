import { useState, useEffect, useCallback, useRef } from 'react';
import { flushOutbox, counts } from './offline';

// Debounce a fast-changing value (e.g. a search box) so effects fire after the
// user pauses. Screens previously re-implemented this inline with setTimeout.
export function useDebounce(value, ms = 250) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

// Render a Chart.js chart into a <canvas> ref, destroying/recreating it when the
// config changes and on unmount. Replaces the copy-pasted new window.Chart(...)
// + cleanup blocks across Dashboard/Finance/Results. `make` returns a Chart
// config object (or null to skip). Returns the canvas ref to spread onto <canvas>.
export function useChart(make, deps) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current || !window.Chart) return undefined;
    let cfg;
    try { cfg = make(); } catch (e) { cfg = null; }
    if (!cfg) return undefined;
    const chart = new window.Chart(ref.current, cfg);
    return () => { try { chart.destroy(); } catch (e) { /* noop */ } };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  return ref;
}

// The grid/axis colour Chart.js should use, read from the live theme so charts
// follow light/dark. Call inside a chart config.
export function chartInk() {
  const cs = getComputedStyle(document.documentElement);
  return {
    text: (cs.getPropertyValue('--text-secondary') || '#475569').trim(),
    grid: 'rgba(128,128,128,.15)',
  };
}

// Animate a number from 0 up to `target` over `ms`, easing out. Returns the
// current value; updates via requestAnimationFrame. Honours
// prefers-reduced-motion (and SSR/no-rAF) by jumping straight to the target.
export function useCountUp(target, { ms = 900 } = {}) {
  const [val, setVal] = useState(target || 0);
  useEffect(() => {
    if (target == null) return undefined;
    const reduce = typeof window !== 'undefined' && window.matchMedia
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce || typeof requestAnimationFrame === 'undefined' || ms <= 0) { setVal(target); return undefined; }
    let raf, start;
    const tick = (t) => {
      if (start == null) start = t;
      const p = Math.min(1, (t - start) / ms);
      const eased = 1 - Math.pow(1 - p, 3); // easeOutCubic
      setVal(target * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
      else setVal(target);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return val;
}

// Track connectivity.
export function useOnline() {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener('online', up);
    window.addEventListener('offline', down);
    return () => { window.removeEventListener('online', up); window.removeEventListener('offline', down); };
  }, []);
  return online;
}

// Outbox sync: flush on reconnect, on mount, and every 30s; expose counts.
export function useSync() {
  const [state, setState] = useState({ pending: 0, failed: 0 });
  const refresh = useCallback(async () => setState(await counts()), []);
  const flush = useCallback(async () => { const r = await flushOutbox(); await refresh(); return r; }, [refresh]);
  useEffect(() => {
    refresh();
    const up = () => flush();
    window.addEventListener('online', up);
    const timer = setInterval(() => { if (navigator.onLine) flush(); }, 30000);
    if (navigator.onLine) flush();
    return () => { window.removeEventListener('online', up); clearInterval(timer); };
  }, [flush, refresh]);
  return { ...state, flush, refresh };
}

// Small data-loading helper with loading/error/stale (cached) states.
export function useAsync(fn, deps) {
  const [state, setState] = useState({ loading: true });
  const run = useCallback(() => {
    let alive = true;
    setState({ loading: true });
    Promise.resolve(fn())
      .then((data) => { if (alive) setState({ loading: false, data }); })
      .catch((error) => { if (alive) setState({ loading: false, error }); });
    return () => { alive = false; };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(run, [run]);
  return [state, run];
}
