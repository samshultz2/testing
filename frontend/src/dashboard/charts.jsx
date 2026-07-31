import React, { useEffect, useRef } from 'react';
import { applyChartDefaults } from '../lib/hooks';

// Theme-aware axis/grid colours. NOTE: canvas can't read CSS vars, so `tick`
// must be a resolved colour — passing 'var(--…)' falls back to Chart.js's dark
// grey (unreadable in dark mode).
export const chartTheme = () => {
  const dark = document.documentElement.getAttribute('data-theme') === 'dark';
  const cs = getComputedStyle(document.documentElement);
  return {
    grid: dark ? 'rgba(255,255,255,.08)' : 'rgba(0,0,0,.06)',
    tick: (cs.getPropertyValue('--text-muted') || (dark ? '#94a0b4' : '#5b6675')).trim(),
  };
};

// Thin React wrapper over the globally-loaded Chart.js (vendored umd build).
// Data is static per page load, so the chart is built once on mount.
export default function Chart({ type, data, options, ariaLabel }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current || !window.Chart) return undefined;
    window.Chart.defaults.color = chartTheme().tick;
    const chart = new window.Chart(ref.current, { type, data, options: options || {} });
    return () => chart.destroy();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  // The canvas is opaque to assistive tech; role="img" + a text summary give
  // screen readers the gist. Fall back to the type when no label is supplied.
  return <canvas ref={ref} role="img" aria-label={ariaLabel || (type + ' chart')} />;
}
