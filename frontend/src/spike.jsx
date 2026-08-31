/*
 * React integration spike — proves build / mount / auth / offline on the real
 * stack. Renders one read-only widget from /api/dashboard/stats (students
 * module — same gate as the pages it's mounted on) as a Chart.js doughnut,
 * reusing the Chart.js already loaded globally by base.html.
 */
import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';

function csrfToken() {
  const m = document.querySelector('meta[name="csrf-token"]');
  return m ? m.getAttribute('content') : '';
}

async function apiGet(url) {
  const res = await fetch(url, {
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'fetch' },
  });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  const ct = res.headers.get('content-type') || '';
  if (!ct.includes('application/json')) throw new Error('expected JSON, got ' + ct);
  return res.json();
}

// React component that drives a Chart.js doughnut (the lib is global, loaded by
// base.html — so it's not bundled here, just used).
function Doughnut({ labels, data, colors }) {
  const canvas = useRef(null);
  const chart = useRef(null);
  useEffect(() => {
    if (!canvas.current || !window.Chart) return;
    chart.current = new window.Chart(canvas.current, {
      type: 'doughnut',
      data: { labels, datasets: [{ data, backgroundColor: colors, borderWidth: 0 }] },
      options: { cutout: '62%', plugins: { legend: { position: 'bottom' } } },
    });
    return () => chart.current && chart.current.destroy();
  }, [labels.join('|'), data.join('|')]);
  return <canvas ref={canvas} height="180" aria-label="students by gender" />;
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
    return <p style={{ color: 'var(--danger)' }}>Couldn’t load: {state.error}</p>;

  const s = state.data || {};
  const male = s.male_students || 0;
  const female = s.female_students || 0;
  const total = s.total_students ?? male + female;
  return (
    <div style={{ maxWidth: 320 }}>
      <Doughnut labels={['Male', 'Female']} data={[male, female]} colors={['#4CAF50', '#E91E63']} />
      <p style={{ marginTop: 8, fontSize: 'var(--text-sm)', textAlign: 'center' }}>
        Total active students: <b>{total}</b>
      </p>
      <p style={{ marginTop: 6, fontSize: 'var(--text-xs)', color: 'var(--success)', textAlign: 'center' }}>
        ✓ React + Chart.js, via <code>/api/dashboard/stats</code> (cookie + CSRF, offline-cached)
      </p>
    </div>
  );
}

const mount = document.getElementById('react-spike');
if (mount) createRoot(mount).render(<StatsWidget />);
