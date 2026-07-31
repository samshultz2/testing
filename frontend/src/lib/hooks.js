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

// Global Chart.js defaults — resolved, theme-aware colours plus premium
// touches (rounded bars, soft grid, point-style legends, themed tooltips,
// smooth entry animation). IMPORTANT: charts draw on <canvas>, which cannot
// parse CSS variables — passing 'var(--x)' silently falls back to Chart.js's
// dark-grey default, which is why axis labels were unreadable in dark mode.
// We resolve every colour to a real value here.
export function applyChartDefaults() {
  const C = window.Chart;
  if (!C || !C.defaults) return;
  const cs = getComputedStyle(document.documentElement);
  const dark = document.documentElement.getAttribute('data-theme') === 'dark';
  const muted = (cs.getPropertyValue('--text-muted') || (dark ? '#94a0b4' : '#5b6675')).trim();
  const grid = dark ? 'rgba(255,255,255,.09)' : 'rgba(15,23,42,.07)';
  C.defaults.color = muted;                 // all tick/label/legend text
  C.defaults.borderColor = grid;            // grid lines default to this
  if (C.defaults.font) {
    C.defaults.font.family = "'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
    C.defaults.font.size = 12;
  }
  try { C.defaults.elements.bar.borderRadius = 6; C.defaults.elements.bar.borderSkipped = false; } catch (e) { /* noop */ }
  try { C.defaults.elements.point.radius = 3; C.defaults.elements.point.hoverRadius = 5; C.defaults.elements.line.tension = 0.35; } catch (e) { /* noop */ }
  try { C.defaults.animation.duration = 600; C.defaults.animation.easing = 'easeOutQuart'; } catch (e) { /* noop */ }
  try {
    const tt = C.defaults.plugins.tooltip;
    tt.backgroundColor = dark ? '#182031' : '#0f172a';
    tt.titleColor = '#fff'; tt.bodyColor = dark ? '#dbe2ec' : '#e2e8f0';
    tt.borderColor = dark ? 'rgba(255,255,255,.10)' : 'rgba(255,255,255,.08)';
    tt.borderWidth = 1; tt.padding = 10; tt.cornerRadius = 8; tt.boxPadding = 4; tt.usePointStyle = true;
  } catch (e) { /* noop */ }
  try { C.defaults.plugins.legend.labels.usePointStyle = true; C.defaults.plugins.legend.labels.boxWidth = 8; C.defaults.plugins.legend.labels.padding = 14; } catch (e) { /* noop */ }
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
    applyChartDefaults();
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

// A sophisticated, harmonious chart palette — muted and presentation-quality,
// not the loud primary blue/red of a default admin panel. Slightly brighter in
// dark mode so series stay legible on the deep surface. Use for all chart
// series so every graph across the app reads as one considered system.
export function chartPalette() {
  const dark = document.documentElement.getAttribute('data-theme') === 'dark'
    || (getComputedStyle(document.documentElement).getPropertyValue('--bg-body').trim().startsWith('#0'));
  const light = {
    green: '#2f9e83', indigo: '#6d74d6', amber: '#e0a63a', rose: '#d47a86',
    cyan: '#3aa6c2', violet: '#9b7ede', slate: '#94a3b8', teal: '#2f9e83',
  };
  const dk = {
    green: '#43b89c', indigo: '#8b93ef', amber: '#f0bd5a', rose: '#e694a0',
    cyan: '#5cc0da', violet: '#b49bf0', slate: '#8f9bb0', teal: '#43b89c',
  };
  const c = dark ? dk : light;
  return {
    ...c,
    // Gender: a calm indigo / muted rose instead of loud blue / fire red.
    male: c.indigo, female: c.rose,
    // Ordered categorical ramp for multi-series / doughnut charts.
    categorical: [c.green, c.indigo, c.amber, c.rose, c.cyan, c.violet, c.slate],
    // Soft fill for area/line charts (brand green at low opacity).
    fill: dark ? 'rgba(67,184,156,.14)' : 'rgba(47,158,131,.12)',
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
