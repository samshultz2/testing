/*
 * React integration spike — proves the four risky points on the real stack:
 *   1. Build    : this JSX is bundled (with React) by esbuild -> static/js/react/spike.js
 *   2. Mount    : hydrates the #react-spike div in a Jinja page
 *   3. Auth     : fetch() uses the session cookie + the <meta name="csrf-token"> header
 *   4. Offline  : the bundle is precached by the service worker (see static/js/sw.js)
 *
 * It renders one read-only widget from /api/dashboard/stats (main blueprint,
 * "students" module — the same module that gates this page, so any user who can
 * open /react-spike can read it). No new backend.
 */
import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';

// CSRF token from the meta tag — utils/csrf.py accepts it as the X-CSRFToken
// header (a no-op on GET, but proves the wiring for future POST/PUT/DELETE).
function csrfToken() {
  const m = document.querySelector('meta[name="csrf-token"]');
  return m ? m.getAttribute('content') : '';
}

async function apiGet(url) {
  const res = await fetch(url, {
    credentials: 'same-origin',
    headers: {
      'X-CSRFToken': csrfToken(),
      // Tells the access gate this is an API call, so a denied request returns
      // a JSON 403 instead of an HTML redirect (which fetch would choke on).
      'X-Requested-With': 'fetch',
    },
  });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  const ct = res.headers.get('content-type') || '';
  if (!ct.includes('application/json')) throw new Error('expected JSON, got ' + ct);
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

function StatsWidget() {
  const [state, setState] = useState({ loading: true });
  useEffect(() => {
    apiGet('/api/dashboard/stats')
      .then((d) => setState({ loading: false, data: d }))
      .catch((e) => setState({ loading: false, error: String(e) }));
  }, []);

  if (state.loading) return <p style={{ color: '#888' }}>Loading…</p>;
  if (state.error)
    return <p style={{ color: '#dc2626' }}>Couldn’t load: {state.error}</p>;

  const s = state.data || {};
  const male = s.male_students || 0;
  const female = s.female_students || 0;
  const max = Math.max(1, male, female);
  return (
    <div>
      <Bar label="Male" value={male} max={max} color="#4CAF50" />
      <Bar label="Female" value={female} max={max} color="#E91E63" />
      <p style={{ marginTop: 8, fontSize: 13 }}>
        Total active students: <b>{s.total_students ?? male + female}</b>
      </p>
      <p style={{ marginTop: 6, fontSize: 12, color: '#16a34a' }}>
        ✓ Rendered by React from <code>/api/dashboard/stats</code> — session cookie + CSRF header, cached for offline.
      </p>
    </div>
  );
}

const mount = document.getElementById('react-spike');
if (mount) createRoot(mount).render(<StatsWidget />);
