import React from 'react';
import { createRoot } from 'react-dom/client';
import ParentApp from './parent/ParentApp';

function initial() {
  const el = document.getElementById('parent-data');
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}

const mount = document.getElementById('parent-app');
const data = initial();
if (mount) {
  createRoot(mount).render(
    data ? <ParentApp data={data} /> : <p className="muted" style={{ padding: '2rem', textAlign: 'center' }}>Couldn’t load the portal. Please refresh.</p>
  );
}
