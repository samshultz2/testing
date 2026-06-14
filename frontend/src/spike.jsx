/*
 * React integration spike — proves the four risky points on the real stack:
 *   1. Build    : this JSX is bundled (with React) by esbuild -> static/js/react/spike.js
 *   2. Mount    : hydrates the #react-spike div in a Jinja page
 *   3. Auth     : fetch() uses the session cookie + the <meta name="csrf-token"> header
 *   4. Offline  : the bundle is precached by the service worker (see static/js/sw.js)
 *
 * It renders one read-only widget from the existing charts API. No new backend.
 */
import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';

// CSRF token from the meta tag — same mechanism the rest of the app uses
// (utils/csrf.py accepts it as the X-CSRFToken header). A no-op on GET, but it
// proves the wiring for future POST/PUT/DELETE from React.
function csrfToken() {
  const m = document.querySelector('meta[name="csrf-token"]');
  return m ? m.getAttribute('content') : '';
}

async function apiGet(url) {
  const res = await fetch(url, {
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': csrfToken() },
  });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}

function Bar({ label, value, max, color }) {
  const pct = max ? Math.round((value / max) * 100) : 0;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '6px 0' }}>
      <div style={{ width: 96, fontSize: 13 }}>{label}</div>
      <div style={{ flex: 1, background: '#eef2f7', borderRadius: 6, overflow: 'hidden' }}>
        <div style={{ width: pct + '%', minWidth: 2, height: 18, background: color || '#2563eb' }} />
      </div>
      <div style={{ width: 40, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{value}</div>
    </div>
  );
}

function GenderWidget() {
  const [state, setState] = useState({ loading: true });
  useEffect(() => {
    apiGet('/reports/api/charts/gender-distribution')
      .then((d) => setState({ loading: false, data: d }))
      .catch((e) => setState({ loading: false, error: String(e) }));
  }, []);

  if (state.loading) return <p style={{ color: '#888' }}>Loading…</p>;
  if (state.error)
    return <p style={{ color: '#dc2626' }}>Couldn’t load: {state.error}</p>;

  const { labels = [], data = [], backgroundColor = [] } = state.data || {};
  const max = Math.max(1, ...data);
  return (
    <div>
      {labels.map((label, i) => (
        <Bar key={label} label={label} value={data[i]} max={max} color={backgroundColor[i]} />
      ))}
      <p style={{ marginTop: 10, fontSize: 12, color: '#16a34a' }}>
        ✓ Rendered by React from <code>/reports/api/charts/gender-distribution</code> — session cookie + CSRF header, cached for offline.
      </p>
    </div>
  );
}

const mount = document.getElementById('react-spike');
if (mount) createRoot(mount).render(<GenderWidget />);
