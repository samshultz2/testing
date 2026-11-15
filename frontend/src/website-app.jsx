import React from 'react';
import { createRoot } from 'react-dom/client';
import WebsiteApp from './website/App';
import { ErrorState } from './components/ui';

function initial() {
  const el = document.getElementById('web-data');
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}

const mount = document.getElementById('web-app');
const data = initial();
if (mount) {
  createRoot(mount).render(
    data ? <WebsiteApp data={data} /> : <ErrorState title="Couldn’t load the Website Builder" detail="Please refresh." />
  );
}
