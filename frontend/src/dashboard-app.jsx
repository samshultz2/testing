import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './dashboard/App';

// Data is hydrated inline by the server (no round-trip). Falls back to an
// empty object so the shell still renders if the script tag is missing.
function readData() {
  const el = document.getElementById('dash-data');
  if (!el) return {};
  try { return JSON.parse(el.textContent); } catch (e) { return {}; }
}

const mount = document.getElementById('dashboard-app');
if (mount) createRoot(mount).render(<App data={readData()} />);
