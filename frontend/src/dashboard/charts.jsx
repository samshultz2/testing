import React, { useEffect, useRef } from 'react';

// Theme-aware axis/grid colours, matching the classic dashboard script.
export const chartTheme = () => {
  const dark = document.documentElement.getAttribute('data-theme') === 'dark';
  return {
    grid: dark ? 'rgba(255,255,255,.08)' : 'rgba(0,0,0,.06)',
    tick: dark ? 'var(--text-muted)' : 'var(--text-muted)',
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
